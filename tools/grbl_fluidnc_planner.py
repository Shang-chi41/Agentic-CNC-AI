"""GRBL/FluidNC-like planner utilities for Mission 04.

This module is dependency-free and safe to run on a clean Windows project.
It is not a byte-for-byte copy of GRBL/FluidNC. It implements the subset that
is useful for the CNC Digital Twin verification loop:

- G20/G21 units
- G90/G91 distance mode
- G54..G59 work coordinate systems
- G10 L2 P1..P6 work offset programming
- G92 coordinate offset
- G0/G1 linear moves
- G2/G3 XY-plane arcs with I/J or R, linearized into short segments
- soft-limit rejection
- simple two-pass look-ahead/junction velocity annotation

The output is a list of PlannedSegment records that can be used by virtual-lab,
MATLAB validation scripts, or report evidence generation.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Iterable

AXES = ("x", "y", "z")
GCODE_RE = re.compile(r"([A-Za-z])\s*([-+]?\d*\.?\d+(?:[Ee][-+]?\d+)?)")
FLOAT_TOL = 1e-9


@dataclass
class PlannerConfig:
    max_feed_mms: float = 8.3333333333
    rapid_mms: float = 8.3333333333
    accel_mms2: float = 10.0
    arc_segment_mm: float = 1.0
    min_arc_segments: int = 4
    max_arc_segments: int = 720
    junction_deviation_mm: float = 0.05
    soft_min_x: float = -1.0e9
    soft_max_x: float = 1.0e9
    soft_min_y: float = -1.0e9
    soft_max_y: float = 1.0e9
    soft_min_z: float = -1.0e9
    soft_max_z: float = 1.0e9

    def soft_min(self) -> tuple[float, float, float]:
        return (self.soft_min_x, self.soft_min_y, self.soft_min_z)

    def soft_max(self) -> tuple[float, float, float]:
        return (self.soft_max_x, self.soft_max_y, self.soft_max_z)


@dataclass
class PlannedSegment:
    seq: int
    source_line: str
    motion: str
    start_x: float
    start_y: float
    start_z: float
    end_x: float
    end_y: float
    end_z: float
    length_mm: float
    feed_mms: float
    nominal_mms: float
    entry_mms: float = 0.0
    exit_mms: float = 0.0
    max_entry_mms: float = 0.0
    junction_angle_deg: float = 0.0
    wcs: str = "G54"
    status: str = "OK"
    notes: str = ""

    def direction(self) -> tuple[float, float, float]:
        if self.length_mm <= FLOAT_TOL:
            return (0.0, 0.0, 0.0)
        return (
            (self.end_x - self.start_x) / self.length_mm,
            (self.end_y - self.start_y) / self.length_mm,
            (self.end_z - self.start_z) / self.length_mm,
        )


@dataclass
class PlannerResult:
    status: str
    segments: list[PlannedSegment]
    final_machine: tuple[float, float, float]
    final_work: tuple[float, float, float]
    active_wcs: str
    work_offsets: dict[str, tuple[float, float, float]]
    g92_offset: tuple[float, float, float]
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "segments": [asdict(s) for s in self.segments],
            "final_machine": self.final_machine,
            "final_work": self.final_work,
            "active_wcs": self.active_wcs,
            "work_offsets": self.work_offsets,
            "g92_offset": self.g92_offset,
            "warnings": self.warnings,
            "errors": self.errors,
        }


class PlannerError(ValueError):
    pass


def clean_gcode(gcode: str) -> list[str]:
    lines: list[str] = []
    for raw in gcode.splitlines():
        line = raw.split(";", 1)[0]
        line = re.sub(r"\([^)]*\)", "", line).strip()
        if not line:
            continue
        # Drop line numbers and checksums, common in GRBL streams.
        line = re.sub(r"^\s*N\d+\s*", "", line, flags=re.IGNORECASE)
        line = line.split("*", 1)[0].strip()
        if line:
            lines.append(line.upper())
    return lines


def parse_words_multi(line: str) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {}
    for key, value in GCODE_RE.findall(line):
        out.setdefault(key.upper(), []).append(float(value))
    return out


def first_word(words: dict[str, list[float]], key: str, default: float | None = None) -> float | None:
    vals = words.get(key.upper())
    if not vals:
        return default
    return vals[0]


def has_g(words: dict[str, list[float]], code: int) -> bool:
    return any(int(round(v)) == code for v in words.get("G", []))


def has_m(words: dict[str, list[float]], code: int) -> bool:
    return any(int(round(v)) == code for v in words.get("M", []))


def vec_add(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def vec_sub(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vec_len(v: tuple[float, float, float]) -> float:
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def clamp(v: float, lo: float, hi: float) -> float:
    return min(max(v, lo), hi)


def within_soft_limits(p: tuple[float, float, float], cfg: PlannerConfig) -> bool:
    mn = cfg.soft_min(); mx = cfg.soft_max()
    return all(mn[i] - FLOAT_TOL <= p[i] <= mx[i] + FLOAT_TOL for i in range(3))


def wcs_name(index: int) -> str:
    return f"G{54 + index}"


def _target_from_words(
    words: dict[str, list[float]],
    current_work: tuple[float, float, float],
    unit_scale: float,
    absolute: bool,
) -> tuple[float, float, float]:
    target = list(current_work)
    for i, axis in enumerate(("X", "Y", "Z")):
        value = first_word(words, axis)
        if value is None:
            continue
        scaled = value * unit_scale
        target[i] = scaled if absolute else target[i] + scaled
    return (target[0], target[1], target[2])


def _arc_centers_from_r(
    start_xy: tuple[float, float],
    end_xy: tuple[float, float],
    radius: float,
    clockwise: bool,
) -> tuple[float, float]:
    sx, sy = start_xy
    ex, ey = end_xy
    dx, dy = ex - sx, ey - sy
    chord = math.hypot(dx, dy)
    if chord < FLOAT_TOL:
        raise PlannerError("G2/G3 with R cannot have identical XY start/end")
    r_abs = abs(radius)
    if chord > 2.0 * r_abs + 1e-7:
        raise PlannerError(f"Arc R too small for chord: R={radius}, chord={chord}")
    mx, my = (sx + ex) / 2.0, (sy + ey) / 2.0
    h = math.sqrt(max(0.0, r_abs * r_abs - (chord / 2.0) ** 2))
    nx, ny = -dy / chord, dx / chord
    c1 = (mx + nx * h, my + ny * h)
    c2 = (mx - nx * h, my - ny * h)

    def sweep_for(center: tuple[float, float]) -> float:
        a0 = math.atan2(sy - center[1], sx - center[0])
        a1 = math.atan2(ey - center[1], ex - center[0])
        if clockwise:
            sweep = a1 - a0
            if sweep >= 0:
                sweep -= 2.0 * math.pi
        else:
            sweep = a1 - a0
            if sweep <= 0:
                sweep += 2.0 * math.pi
        return sweep

    s1 = sweep_for(c1)
    s2 = sweep_for(c2)
    # Positive R selects the shorter arc; negative R selects the longer arc.
    if radius >= 0:
        return c1 if abs(s1) <= abs(s2) else c2
    return c1 if abs(s1) > abs(s2) else c2


def _linearized_arc_points(
    start_machine: tuple[float, float, float],
    end_machine: tuple[float, float, float],
    words: dict[str, list[float]],
    unit_scale: float,
    clockwise: bool,
    cfg: PlannerConfig,
) -> list[tuple[float, float, float]]:
    sx, sy, sz = start_machine
    ex, ey, ez = end_machine
    i = first_word(words, "I")
    j = first_word(words, "J")
    r = first_word(words, "R")
    if i is not None or j is not None:
        cx = sx + (i or 0.0) * unit_scale
        cy = sy + (j or 0.0) * unit_scale
    elif r is not None:
        cx, cy = _arc_centers_from_r((sx, sy), (ex, ey), r * unit_scale, clockwise)
    else:
        raise PlannerError("G2/G3 requires I/J or R in the XY plane")

    radius0 = math.hypot(sx - cx, sy - cy)
    radius1 = math.hypot(ex - cx, ey - cy)
    if radius0 < FLOAT_TOL:
        raise PlannerError("Arc start radius is zero")
    if abs(radius0 - radius1) > max(0.05, 0.01 * radius0):
        raise PlannerError(f"Arc radius mismatch start={radius0:.6g}, end={radius1:.6g}")

    a0 = math.atan2(sy - cy, sx - cx)
    a1 = math.atan2(ey - cy, ex - cx)
    if clockwise:
        sweep = a1 - a0
        if sweep >= 0:
            sweep -= 2.0 * math.pi
    else:
        sweep = a1 - a0
        if sweep <= 0:
            sweep += 2.0 * math.pi

    arc_len = abs(sweep) * radius0
    helical_len = math.sqrt(arc_len * arc_len + (ez - sz) * (ez - sz))
    n = int(math.ceil(max(helical_len / max(cfg.arc_segment_mm, 1e-6), cfg.min_arc_segments)))
    n = int(clamp(n, cfg.min_arc_segments, cfg.max_arc_segments))
    points: list[tuple[float, float, float]] = []
    for step in range(1, n + 1):
        f = step / n
        a = a0 + sweep * f
        x = cx + radius0 * math.cos(a)
        y = cy + radius0 * math.sin(a)
        z = sz + (ez - sz) * f
        if step == n:
            x, y, z = ex, ey, ez
        points.append((x, y, z))
    return points


def _append_segment(
    out: list[PlannedSegment],
    source_line: str,
    motion: str,
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    feed_mms: float,
    nominal_mms: float,
    active_wcs: str,
    cfg: PlannerConfig,
    errors: list[str],
) -> None:
    if not within_soft_limits(end, cfg):
        errors.append(f"Soft limit violation at line '{source_line}': target={end}")
        return
    length = vec_len(vec_sub(end, start))
    if length <= FLOAT_TOL:
        return
    out.append(
        PlannedSegment(
            seq=len(out) + 1,
            source_line=source_line,
            motion=motion,
            start_x=start[0], start_y=start[1], start_z=start[2],
            end_x=end[0], end_y=end[1], end_z=end[2],
            length_mm=length,
            feed_mms=feed_mms,
            nominal_mms=min(max(1e-6, feed_mms), cfg.max_feed_mms),
            wcs=active_wcs,
        )
    )


def apply_lookahead(segments: list[PlannedSegment], cfg: PlannerConfig) -> None:
    if not segments:
        return
    accel = max(cfg.accel_mms2, 1e-6)
    # Junction pass: estimate corner speed from vector angle. This is a stable,
    # reportable approximation rather than exact GRBL planner.cpp internals.
    for i, seg in enumerate(segments):
        if i == 0:
            seg.max_entry_mms = 0.0
            seg.entry_mms = 0.0
            continue
        prev = segments[i - 1]
        u = prev.direction()
        v = seg.direction()
        dot = clamp(u[0] * v[0] + u[1] * v[1] + u[2] * v[2], -1.0, 1.0)
        angle = math.acos(dot)
        seg.junction_angle_deg = math.degrees(angle)
        if angle < math.radians(1.0):
            max_junction = min(prev.nominal_mms, seg.nominal_mms)
            seg.notes = "near-collinear; continuous junction"
        elif angle > math.radians(175.0):
            max_junction = 0.0
            seg.notes = "reversal/near-stop junction"
        else:
            sin_half = math.sin(angle / 2.0)
            # Conservative junction model inspired by GRBL's junction-deviation concept.
            max_junction = math.sqrt(max(0.0, accel * cfg.junction_deviation_mm * sin_half / max(1e-9, 1.0 - sin_half)))
            max_junction = min(max_junction, prev.nominal_mms, seg.nominal_mms)
            seg.notes = "junction-limited"
        seg.max_entry_mms = max_junction

    # Reverse pass: can decelerate from next entry.
    next_entry = 0.0
    for i in range(len(segments) - 1, -1, -1):
        seg = segments[i]
        allowable = math.sqrt(max(0.0, next_entry * next_entry + 2.0 * accel * seg.length_mm))
        seg.exit_mms = min(next_entry, seg.nominal_mms)
        seg.entry_mms = min(seg.nominal_mms, seg.max_entry_mms if i > 0 else 0.0, allowable)
        next_entry = seg.entry_mms

    # Forward pass: cannot accelerate beyond segment length.
    prev_exit = 0.0
    for seg in segments:
        allowable = math.sqrt(max(0.0, prev_exit * prev_exit + 2.0 * accel * seg.length_mm))
        seg.entry_mms = min(seg.entry_mms, allowable, seg.nominal_mms)
        prev_exit = min(seg.nominal_mms, seg.exit_mms if seg.exit_mms > 0 else seg.nominal_mms)


def plan_gcode(gcode: str, cfg: PlannerConfig | None = None) -> PlannerResult:
    cfg = cfg or PlannerConfig()
    lines = clean_gcode(gcode)
    unit_scale = 1.0
    absolute = True
    motion_mode = 0
    feed_mms = 300.0 / 60.0
    active_wcs_idx = 0
    work_offsets = [(0.0, 0.0, 0.0) for _ in range(6)]
    g92_offset = (0.0, 0.0, 0.0)
    machine_pos = (0.0, 0.0, 0.0)
    work_pos = (0.0, 0.0, 0.0)
    warnings: list[str] = []
    errors: list[str] = []
    segments: list[PlannedSegment] = []

    def work_to_machine(p: tuple[float, float, float]) -> tuple[float, float, float]:
        return vec_add(vec_add(p, work_offsets[active_wcs_idx]), g92_offset)

    def sync_work_from_machine() -> tuple[float, float, float]:
        return vec_sub(vec_sub(machine_pos, work_offsets[active_wcs_idx]), g92_offset)

    for line in lines:
        words = parse_words_multi(line)
        if has_m(words, 2) or has_m(words, 30):
            break
        if has_g(words, 20):
            unit_scale = 25.4
        if has_g(words, 21):
            unit_scale = 1.0
        if has_g(words, 90):
            absolute = True
        if has_g(words, 91):
            absolute = False
        for code in range(54, 60):
            if has_g(words, code):
                active_wcs_idx = code - 54
                work_pos = sync_work_from_machine()
        if has_g(words, 0):
            motion_mode = 0
        if has_g(words, 1):
            motion_mode = 1
        if has_g(words, 2):
            motion_mode = 2
        if has_g(words, 3):
            motion_mode = 3
        f = first_word(words, "F")
        if f is not None:
            feed_mms = max(0.001, f * unit_scale / 60.0)

        # G10 L2 Pn X/Y/Z sets work offset n=1..6. This is enough for repeatable
        # Mission 04 validation and mirrors the common GRBL/FluidNC workflow.
        if has_g(words, 10) and int(round(first_word(words, "L", 0.0) or 0.0)) == 2:
            p = int(round(first_word(words, "P", 1.0) or 1.0))
            if 1 <= p <= 6:
                cur = list(work_offsets[p - 1])
                for i, axis in enumerate(("X", "Y", "Z")):
                    value = first_word(words, axis)
                    if value is not None:
                        cur[i] = value * unit_scale
                work_offsets[p - 1] = (cur[0], cur[1], cur[2])
                if p - 1 == active_wcs_idx:
                    work_pos = sync_work_from_machine()
            else:
                errors.append(f"Unsupported G10 P value at line '{line}'")
            continue

        if has_g(words, 92):
            specified = list(work_pos)
            for i, axis in enumerate(("X", "Y", "Z")):
                value = first_word(words, axis)
                if value is not None:
                    specified[i] = value * unit_scale
            work_pos = (specified[0], specified[1], specified[2])
            g92_offset = vec_sub(machine_pos, vec_add(work_pos, work_offsets[active_wcs_idx]))
            continue

        if has_g(words, 92) and int(round(first_word(words, "G", 92) or 92)) in (921, 922, 923):
            warnings.append("G92.1/G92.2/G92.3 are not parsed by the lightweight planner")

        has_axis = any(axis in words for axis in ("X", "Y", "Z"))
        if not has_axis or motion_mode not in (0, 1, 2, 3):
            continue

        target_work = _target_from_words(words, work_pos, unit_scale, absolute)
        target_machine = work_to_machine(target_work)
        active_name = wcs_name(active_wcs_idx)
        nominal = cfg.rapid_mms if motion_mode == 0 else feed_mms
        motion = {0: "G0", 1: "G1", 2: "G2", 3: "G3"}[motion_mode]
        if motion_mode in (0, 1):
            _append_segment(segments, line, motion, machine_pos, target_machine, nominal, nominal, active_name, cfg, errors)
        else:
            try:
                points = _linearized_arc_points(machine_pos, target_machine, words, unit_scale, clockwise=(motion_mode == 2), cfg=cfg)
                start = machine_pos
                for point in points:
                    _append_segment(segments, line, motion, start, point, nominal, nominal, active_name, cfg, errors)
                    start = point
            except PlannerError as exc:
                errors.append(f"{line}: {exc}")
        if errors:
            break
        machine_pos = target_machine
        work_pos = target_work

    apply_lookahead(segments, cfg)
    status = "PASS" if not errors else "FAIL"
    return PlannerResult(
        status=status,
        segments=segments,
        final_machine=machine_pos,
        final_work=work_pos,
        active_wcs=wcs_name(active_wcs_idx),
        work_offsets={wcs_name(i): work_offsets[i] for i in range(6)},
        g92_offset=g92_offset,
        warnings=warnings,
        errors=errors,
    )


def write_segments_csv(path: Path, segments: Iterable[PlannedSegment]) -> None:
    rows = [asdict(s) for s in segments]
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _summary_markdown(result: PlannerResult, source: str) -> str:
    segs = result.segments
    total_len = sum(s.length_mm for s in segs)
    max_nom = max((s.nominal_mms for s in segs), default=0.0)
    max_entry = max((s.entry_mms for s in segs), default=0.0)
    arc_count = sum(1 for s in segs if s.motion in ("G2", "G3"))
    linear_count = sum(1 for s in segs if s.motion in ("G0", "G1"))
    lines = [
        "# Mission 04 Planner Summary",
        "",
        f"Source: `{source}`",
        f"Status: **{result.status}**",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Planned segments | {len(segs)} |",
        f"| Linear segments | {linear_count} |",
        f"| Arc-linearized segments | {arc_count} |",
        f"| Total length | {total_len:.6f} mm |",
        f"| Max nominal speed | {max_nom:.6f} mm/s |",
        f"| Max look-ahead entry speed | {max_entry:.6f} mm/s |",
        f"| Final machine X | {result.final_machine[0]:.6f} mm |",
        f"| Final machine Y | {result.final_machine[1]:.6f} mm |",
        f"| Final machine Z | {result.final_machine[2]:.6f} mm |",
        "",
        "## Supported subset",
        "",
        "G20/G21, G90/G91, G54-G59, G10 L2 P1-P6, G92, G0/G1, G2/G3 XY arcs with I/J or R, soft-limit rejection, and conservative look-ahead junction speed annotation.",
    ]
    if result.errors:
        lines.extend(["", "## Errors"] + [f"- {e}" for e in result.errors])
    if result.warnings:
        lines.extend(["", "## Warnings"] + [f"- {w}" for w in result.warnings])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mission 04 GRBL/FluidNC-like planner")
    parser.add_argument("gcode", type=Path, help="G-code file")
    parser.add_argument("--out-dir", type=Path, default=Path("reports/mission4_planner"))
    parser.add_argument("--soft-min", nargs=3, type=float, metavar=("X", "Y", "Z"), default=(-1e9, -1e9, -1e9))
    parser.add_argument("--soft-max", nargs=3, type=float, metavar=("X", "Y", "Z"), default=(1e9, 1e9, 1e9))
    args = parser.parse_args(argv)
    cfg = PlannerConfig(
        soft_min_x=args.soft_min[0], soft_min_y=args.soft_min[1], soft_min_z=args.soft_min[2],
        soft_max_x=args.soft_max[0], soft_max_y=args.soft_max[1], soft_max_z=args.soft_max[2],
    )
    text = args.gcode.read_text(encoding="utf-8")
    result = plan_gcode(text, cfg)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.gcode.stem
    write_segments_csv(args.out_dir / f"{stem}_planned_segments.csv", result.segments)
    (args.out_dir / f"{stem}_planner_result.json").write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    (args.out_dir / f"{stem}_planner_summary.md").write_text(_summary_markdown(result, str(args.gcode)), encoding="utf-8")
    print(f"MISSION04_PLANNER status={result.status} segments={len(result.segments)} final_machine={result.final_machine}")
    if result.errors:
        for e in result.errors:
            print(f"ERROR: {e}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
