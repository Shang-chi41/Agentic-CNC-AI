"""Pure-Python CNC3 virtual lab.

Purpose
-------
Run an end-to-end test without MATLAB, Simulink, MongoDB, FastAPI, NX MCD, or
third-party packages. It is a deterministic replacement for the physical loop:

    HMI/Cloud G-code upload
      -> Edge simulation request
      -> Simulink 3-axis motion model (virtualized here)
      -> CNC3 frame, 116 bytes
      -> Edge JSON normalization
      -> NX MCD 12 LREAL, 96 bytes, big-endian
      -> Mock NX MCD validation

This does not replace the real Simulink axis model. It exists so the protocol,
rate limiting, filtering, numeric sanity, and NX payload contract can be tested
inside a plain VS Code/Python environment.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import struct
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, List, Tuple

CNC3_FRAME_BYTES = 116
NX_LREAL_BYTES = 96
INTERNAL_TS = 5e-5
SEND_HZ = 30.0
SEND_PERIOD = 1.0 / SEND_HZ
VMAX_MMS = 500.0 / 60.0
ACCEL_MMS2 = 10.0
DEFAULT_RAPID_MMS = VMAX_MMS
DEFAULT_FEED_MMS = 400.0 / 60.0

GCODE_RE = re.compile(r"([A-Za-z])\s*([-+]?\d+(?:\.\d+)?)")


@dataclass
class AxisState:
    pos: float = 0.0
    vel: float = 0.0
    accel: float = 0.0
    decel: float = 0.0


@dataclass
class MotionSample:
    t: float
    x: AxisState
    y: AxisState
    z: AxisState
    progress: float
    line: str
    complete: bool = False

    def cnc3_values(self) -> List[float]:
        return [
            self.x.pos, self.x.vel, self.x.accel, self.x.decel,
            self.y.pos, self.y.vel, self.y.accel, self.y.decel,
            self.z.pos, self.z.vel, self.z.accel, self.z.decel,
        ]


@dataclass
class LabReport:
    status: str
    queued_lines: int
    motion_blocks: int
    cnc3_frames: int
    nx_frames: int
    first_nx_values: List[float]
    last_nx_values: List[float]
    max_x: float
    max_y: float
    max_z: float
    min_z: float
    max_abs_value: float
    max_send_hz_estimate: float
    cnc3_frame_bytes: int
    nx_lreal_bytes: int
    notes: List[str]


def clean_gcode(gcode: str) -> List[str]:
    lines: List[str] = []
    for raw in gcode.splitlines():
        # strip semicolon comments and parenthesized comments
        line = raw.split(";", 1)[0]
        line = re.sub(r"\([^)]*\)", "", line).strip()
        if not line:
            continue
        lines.append(line.upper())
    return lines


def parse_words(line: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for k, v in GCODE_RE.findall(line):
        out[k.upper()] = float(v)
    return out


def pack_cnc3_frame(seq: int, t: float, values: Iterable[float], done: bool = False) -> bytes:
    vals = list(values)
    if len(vals) != 12:
        raise ValueError(f"CNC3 requires 12 values, got {len(vals)}")
    flags = 1 if done else 0
    # Same logical layout as MATLAB Pack_CNC3_Frame:
    # magic CNC3, version uint16, flags uint16, seq uint32, time double, 12 doubles.
    # Use explicit little-endian for bridge-side binary tests.
    return (
        b"CNC3"
        + struct.pack("<HHI", 1, flags, seq)
        + struct.pack("<d", float(t))
        + struct.pack("<" + "d" * 12, *[float(v) for v in vals])
    )


def unpack_cnc3_frame(frame: bytes) -> tuple[int, bool, float, List[float]]:
    if len(frame) != CNC3_FRAME_BYTES:
        raise ValueError(f"bad CNC3 length {len(frame)}")
    if frame[:4] != b"CNC3":
        raise ValueError(f"bad magic {frame[:4]!r}")
    version, flags, seq = struct.unpack("<HHI", frame[4:12])
    if version != 1:
        raise ValueError(f"unsupported version {version}")
    t = struct.unpack("<d", frame[12:20])[0]
    vals = list(struct.unpack("<" + "d" * 12, frame[20:116]))
    return seq, bool(flags & 1), t, vals


def edge_json_from_cnc3(frame: bytes, check_id: str = "virtual-check") -> dict:
    seq, done, t, vals = unpack_cnc3_frame(frame)
    x = vals[0:4]
    y = vals[4:8]
    z = vals[8:12]
    return {
        "protocol": "matlab-edge-json-v1",
        "sequence": seq,
        "mode": "check",
        "check_id": check_id,
        "position": {"x": x[0], "y": y[0], "z": z[0]},
        "velocity": {"x": x[1], "y": y[1], "z": z[1]},
        "acceleration": {"x": x[2], "y": y[2], "z": z[2]},
        "deceleration": {"x": x[3], "y": y[3], "z": z[3]},
        "torque": {"x": 0.0, "y": 0.0, "z": 0.0},
        "progress": 1.0 if done else 0.0,
        "complete": done,
        "success": True,
        "status": "completed" if done else "running",
        "timestamp_s": t,
    }


def edge_to_nx_lreal(payload: dict) -> bytes:
    def get(group: str, axis: str) -> float:
        value = payload.get(group, {}).get(axis, 0.0)
        try:
            f = float(value)
        except Exception:
            f = 0.0
        if math.isnan(f) or math.isinf(f):
            f = 0.0
        return f

    vals = [
        get("position", "x"), get("velocity", "x"), get("acceleration", "x"), get("deceleration", "x"),
        get("position", "y"), get("velocity", "y"), get("acceleration", "y"), get("deceleration", "y"),
        get("position", "z"), get("velocity", "z"), get("acceleration", "z"), get("deceleration", "z"),
    ]
    return struct.pack(">" + "d" * 12, *vals)


def nx_unpack_lreal(data: bytes) -> tuple[float, ...]:
    if len(data) != NX_LREAL_BYTES:
        raise ValueError(f"bad NX LREAL length {len(data)}")
    return struct.unpack(">" + "d" * 12, data)


def trapezoid_move_samples(
    start: tuple[float, float, float],
    target: tuple[float, float, float],
    feed_mms: float,
    start_t: float,
    line: str,
    send_period: float = SEND_PERIOD,
) -> list[MotionSample]:
    dx = target[0] - start[0]
    dy = target[1] - start[1]
    dz = target[2] - start[2]
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length < 1e-12:
        return [MotionSample(start_t, AxisState(start[0]), AxisState(start[1]), AxisState(start[2]), 1.0, line)]

    vmax = max(0.001, min(abs(feed_mms), VMAX_MMS))
    accel = ACCEL_MMS2
    t_accel = vmax / accel
    d_accel = 0.5 * accel * t_accel * t_accel
    if 2.0 * d_accel >= length:
        t_accel = math.sqrt(length / accel)
        t_cruise = 0.0
        v_peak = accel * t_accel
    else:
        d_cruise = length - 2.0 * d_accel
        t_cruise = d_cruise / vmax
        v_peak = vmax
    total_t = 2.0 * t_accel + t_cruise

    ux, uy, uz = dx / length, dy / length, dz / length
    samples: list[MotionSample] = []
    n = max(1, int(math.ceil(total_t / send_period)))
    for i in range(n + 1):
        tau = min(total_t, i * send_period)
        if tau <= t_accel:
            s = 0.5 * accel * tau * tau
            v = accel * tau
            a = accel
            d = 0.0
        elif tau <= t_accel + t_cruise:
            s = 0.5 * accel * t_accel * t_accel + v_peak * (tau - t_accel)
            v = v_peak
            a = 0.0
            d = 0.0
        else:
            td = tau - t_accel - t_cruise
            s = 0.5 * accel * t_accel * t_accel + v_peak * t_cruise + v_peak * td - 0.5 * accel * td * td
            v = max(0.0, v_peak - accel * td)
            a = 0.0
            d = accel
        ratio = min(1.0, max(0.0, s / length))
        x = AxisState(start[0] + ux * s, ux * v, abs(ux) * a, abs(ux) * d)
        y = AxisState(start[1] + uy * s, uy * v, abs(uy) * a, abs(uy) * d)
        z = AxisState(start[2] + uz * s, uz * v, abs(uz) * a, abs(uz) * d)
        samples.append(MotionSample(start_t + i * send_period, x, y, z, ratio, line))
    # Ensure exact final pose.
    samples[-1].x.pos, samples[-1].y.pos, samples[-1].z.pos = target
    samples[-1].x.vel = samples[-1].y.vel = samples[-1].z.vel = 0.0
    samples[-1].x.accel = samples[-1].y.accel = samples[-1].z.accel = 0.0
    samples[-1].x.decel = abs(ux) * ACCEL_MMS2
    samples[-1].y.decel = abs(uy) * ACCEL_MMS2
    samples[-1].z.decel = abs(uz) * ACCEL_MMS2
    return samples


def simulate_gcode(lines: list[str]) -> tuple[list[MotionSample], int]:
    pos = (0.0, 0.0, 0.0)
    absolute = True
    feed = DEFAULT_FEED_MMS
    motion_mode: int | None = None
    t = 0.0
    samples: list[MotionSample] = []
    motion_blocks = 0

    for line in lines:
        words = parse_words(line)
        if "G" in words:
            g = int(round(words["G"]))
            if g == 20:
                raise ValueError("G20 inch mode is not supported in virtual lab; use G21")
            if g == 21:
                continue
            if g == 90:
                absolute = True
                continue
            if g == 91:
                absolute = False
                continue
            if g in (0, 1):
                motion_mode = g
        if "F" in words:
            feed = max(0.001, words["F"] / 60.0)
        if "M" in words and int(round(words["M"])) in (2, 30):
            if samples:
                samples[-1].complete = True
            else:
                samples.append(MotionSample(t, AxisState(pos[0]), AxisState(pos[1]), AxisState(pos[2]), 1.0, line, True))
            break
        has_axis = any(axis in words for axis in ("X", "Y", "Z"))
        if has_axis and motion_mode in (0, 1):
            target = list(pos)
            for idx, axis in enumerate(("X", "Y", "Z")):
                if axis in words:
                    if absolute:
                        target[idx] = words[axis]
                    else:
                        target[idx] += words[axis]
            feed_mms = DEFAULT_RAPID_MMS if motion_mode == 0 else feed
            move = trapezoid_move_samples(pos, tuple(target), feed_mms, t, line)
            if samples and move:
                # avoid duplicate timestamp with last previous final sample
                move = move[1:] if len(move) > 1 else move
            samples.extend(move)
            motion_blocks += 1
            pos = tuple(target)
            if samples:
                t = samples[-1].t + SEND_PERIOD

    if samples and not samples[-1].complete:
        samples[-1].complete = True
    return samples, motion_blocks


def run_virtual_lab(gcode: str, report_path: Path | None = None, verbose: bool = True) -> LabReport:
    lines = clean_gcode(gcode)
    samples, motion_blocks = simulate_gcode(lines)
    if not samples:
        raise AssertionError("No simulation samples generated")

    cnc3_frames: list[bytes] = []
    nx_frames: list[tuple[float, ...]] = []
    timestamps: list[float] = []
    notes: list[str] = []

    for seq, sample in enumerate(samples, start=1):
        frame = pack_cnc3_frame(seq, sample.t, sample.cnc3_values(), done=sample.complete)
        if len(frame) != CNC3_FRAME_BYTES:
            raise AssertionError(f"bad CNC3 frame size: {len(frame)}")
        payload = edge_json_from_cnc3(frame)
        nx = edge_to_nx_lreal(payload)
        if len(nx) != NX_LREAL_BYTES:
            raise AssertionError(f"bad NX frame size: {len(nx)}")
        vals = nx_unpack_lreal(nx)
        cnc3_frames.append(frame)
        nx_frames.append(vals)
        timestamps.append(sample.t)

    xs = [f[0] for f in nx_frames]
    ys = [f[4] for f in nx_frames]
    zs = [f[8] for f in nx_frames]
    all_vals = [v for frame in nx_frames for v in frame]

    if max(xs) < 29.99:
        raise AssertionError(f"X did not reach 30 mm, max={max(xs)}")
    if max(ys) < 9.99:
        raise AssertionError(f"Y did not reach 10 mm, max={max(ys)}")
    if max(zs) < 4.99:
        raise AssertionError(f"Z did not reach safe height 5 mm, max={max(zs)}")
    if any(math.isnan(v) or math.isinf(v) for v in all_vals):
        raise AssertionError("NaN/Inf detected in NX frames")
    if any(abs(v) > 10_000 for v in all_vals):
        raise AssertionError("unreasonable value detected in NX frames")

    intervals = [b - a for a, b in zip(timestamps, timestamps[1:]) if b > a]
    min_period = min(intervals) if intervals else SEND_PERIOD
    hz_est = 1.0 / min_period if min_period > 0 else float("inf")
    if hz_est > SEND_HZ * 1.02:
        raise AssertionError(f"send rate too high: {hz_est:.3f} Hz")
    notes.append("Internal Ts is represented by parameters; virtual output is decimated to 30 Hz.")
    notes.append("NX payload contract verified: 12 big-endian doubles = 96 bytes.")
    notes.append("CNC3 bridge frame contract verified: 116 bytes.")

    report = LabReport(
        status="PASS",
        queued_lines=len(lines),
        motion_blocks=motion_blocks,
        cnc3_frames=len(cnc3_frames),
        nx_frames=len(nx_frames),
        first_nx_values=[round(v, 6) for v in nx_frames[0]],
        last_nx_values=[round(v, 6) for v in nx_frames[-1]],
        max_x=round(max(xs), 6),
        max_y=round(max(ys), 6),
        max_z=round(max(zs), 6),
        min_z=round(min(zs), 6),
        max_abs_value=round(max(abs(v) for v in all_vals), 6),
        max_send_hz_estimate=round(hz_est, 6),
        cnc3_frame_bytes=CNC3_FRAME_BYTES,
        nx_lreal_bytes=NX_LREAL_BYTES,
        notes=notes,
    )

    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(asdict(report), ensure_ascii=False, indent=2), encoding="utf-8")

    if verbose:
        print("PASS CNC3 virtual lab")
        print(f"  queued lines      : {report.queued_lines}")
        print(f"  motion blocks     : {report.motion_blocks}")
        print(f"  CNC3 frames       : {report.cnc3_frames} x {report.cnc3_frame_bytes} bytes")
        print(f"  NX frames         : {report.nx_frames} x {report.nx_lreal_bytes} bytes")
        print(f"  max X/Y/Z         : {report.max_x:.3f}, {report.max_y:.3f}, {report.max_z:.3f} mm")
        print(f"  min Z             : {report.min_z:.3f} mm")
        print(f"  max send Hz       : {report.max_send_hz_estimate:.3f} Hz")
        if report_path:
            print(f"  report            : {report_path}")
    return report


DEFAULT_GCODE = """G21
G90
G0 X0 Y0 Z5
G1 X30 Y10 Z0 F400
G1 X0 Y0 Z0 F400
M30
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Run pure-Python CNC3 virtual lab self-test")
    parser.add_argument("--gcode", type=str, default="", help="Inline G-code text")
    parser.add_argument("--gcode-file", type=Path, default=None, help="Read G-code from file")
    parser.add_argument("--report", type=Path, default=Path("reports/virtual_lab_report.json"))
    args = parser.parse_args()

    if args.gcode_file:
        gcode = args.gcode_file.read_text(encoding="utf-8")
    elif args.gcode:
        gcode = args.gcode
    else:
        gcode = DEFAULT_GCODE
    run_virtual_lab(gcode, report_path=args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
