"""Mission 11 V2 T04: real NX MCD port-6001 capture and calibration.

This tool deliberately does not connect to FluidNC or a physical CNC.  It is a
standalone TCP server used while Siemens NX MCD ``Connection_0`` connects as a
client to 127.0.0.1:6001.

The tool:
- sends the documented 96-byte command frame (12 LREAL values),
- captures the raw NX->Edge byte stream without assuming recv()==frame,
- records recv chunk boundaries and frame counts,
- analyzes the confirmed 100-byte frames as both big- and little-endian,
- emits a fail-closed verdict: CONFIRMED_BIG, CONFIRMED_LITTLE, AMBIGUOUS,
  NO_DATA, or INVALID_CAPTURE.

A real NX run is required before T04 can be marked complete. Synthetic fixtures
only verify the calibration tooling itself at evidence level L2.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import select
import socket
import statistics
import struct
import sys
import time
from typing import Iterable, Optional, Sequence

try:
    from edge_backend.runtime.nx_feedback import (
        NX_FEEDBACK_FRAME_BYTES,
        NXFeedbackSample,
        decode_nx_feedback_frame,
    )
except ModuleNotFoundError:  # pragma: no cover - direct file execution fallback
    ROOT = Path(__file__).resolve().parents[1]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from edge_backend.runtime.nx_feedback import (  # type: ignore[no-redef]
        NX_FEEDBACK_FRAME_BYTES,
        NXFeedbackSample,
        decode_nx_feedback_frame,
    )

COMMAND_LREAL_COUNT = 12
COMMAND_FRAME_BYTES = struct.calcsize(">12d")  # 96
COLLISION_ALLOWED_MASK = 0x0F
VERDICT_CONFIRMED_BIG = "CONFIRMED_BIG"
VERDICT_CONFIRMED_LITTLE = "CONFIRMED_LITTLE"
VERDICT_AMBIGUOUS = "AMBIGUOUS"
VERDICT_NO_DATA = "NO_DATA"
VERDICT_INVALID = "INVALID_CAPTURE"


@dataclass(frozen=True, slots=True)
class ExpectedPose:
    x: float
    y: float
    z: float

    def as_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y, "z": self.z}


@dataclass(frozen=True, slots=True)
class EndianScore:
    endian: str
    label: str
    decoded_frames: int
    decode_failures: int
    plausible_frames: int
    implausible_frames: int
    evaluated_tail_frames: int
    mean_position: dict[str, Optional[float]]
    position_error_max_mean_mm: Optional[float]
    position_error_p95_mm: Optional[float]
    collision_frames: int
    score: float
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["reasons"] = list(self.reasons)
        return result


@dataclass(frozen=True, slots=True)
class TimingMetrics:
    chunk_count: int
    total_bytes: int
    complete_frames: int
    remainder_bytes: int
    capture_duration_s: Optional[float]
    average_frame_rate_hz: Optional[float]
    mean_chunk_bytes: Optional[float]
    median_chunk_bytes: Optional[float]
    p95_chunk_bytes: Optional[float]
    mean_inter_chunk_ms: Optional[float]
    median_inter_chunk_ms: Optional[float]
    p95_inter_chunk_ms: Optional[float]
    chunks_with_multiple_frames: int

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def percentile(values: Sequence[float], percent: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (percent / 100.0)
    low = int(math.floor(rank))
    high = int(math.ceil(rank))
    if low == high:
        return ordered[low]
    weight = rank - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def validate_endian_label(value: str) -> str:
    normalized = str(value).strip().lower()
    aliases = {
        "big": ">",
        ">": ">",
        "network": ">",
        "little": "<",
        "<": "<",
    }
    if normalized not in aliases:
        raise ValueError("endian must be big/'>' or little/'<'")
    return aliases[normalized]


def endian_name(endian: str) -> str:
    return "big" if endian == ">" else "little"


def pack_command_frame(
    *,
    endian: str,
    cp: ExpectedPose,
    velocity_mm_s: float,
    acceleration_mm_s2: float,
    deceleration_mm_s2: float,
) -> bytes:
    """Pack one documented 96-byte Edge->NX command frame."""

    marker = validate_endian_label(endian)
    values = (
        cp.x,
        velocity_mm_s,
        acceleration_mm_s2,
        deceleration_mm_s2,
        cp.y,
        velocity_mm_s,
        acceleration_mm_s2,
        deceleration_mm_s2,
        cp.z,
        velocity_mm_s,
        acceleration_mm_s2,
        deceleration_mm_s2,
    )
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("command values must be finite")
    frame = struct.pack(marker + "12d", *values)
    if len(frame) != COMMAND_FRAME_BYTES:
        raise RuntimeError("command frame contract mismatch")
    return frame


def split_feedback_frames(raw: bytes) -> tuple[list[bytes], bytes]:
    complete = len(raw) // NX_FEEDBACK_FRAME_BYTES
    frames = [
        raw[index * NX_FEEDBACK_FRAME_BYTES : (index + 1) * NX_FEEDBACK_FRAME_BYTES]
        for index in range(complete)
    ]
    remainder = raw[complete * NX_FEEDBACK_FRAME_BYTES :]
    return frames, remainder


def _is_plausible(
    sample: NXFeedbackSample,
    *,
    max_abs_position_mm: float,
    max_abs_velocity_mm_s: float,
    max_abs_acceleration_mm_s2: float,
    max_abs_force: float,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if max(abs(value) for value in sample.position.values()) > max_abs_position_mm:
        reasons.append("position outside configured plausible bound")
    if max(abs(value) for value in sample.velocity.values()) > max_abs_velocity_mm_s:
        reasons.append("velocity outside configured plausible bound")
    if max(abs(value) for value in sample.acceleration.values()) > max_abs_acceleration_mm_s2:
        reasons.append("acceleration outside configured plausible bound")
    if max(abs(value) for value in sample.force.values()) > max_abs_force:
        reasons.append("force outside configured plausible bound")
    return not reasons, reasons


def score_endian(
    frames: Sequence[bytes],
    *,
    endian: str,
    expected_pose: Optional[ExpectedPose],
    position_tolerance_mm: float,
    max_abs_position_mm: float,
    max_abs_velocity_mm_s: float,
    max_abs_acceleration_mm_s2: float,
    max_abs_force: float,
) -> EndianScore:
    samples: list[NXFeedbackSample] = []
    plausible_samples: list[NXFeedbackSample] = []
    failures = 0
    plausible = 0
    implausible = 0
    reasons: list[str] = []

    for sequence, frame in enumerate(frames, start=1):
        try:
            sample = decode_nx_feedback_frame(
                frame,
                endian=endian,
                rx_seq=sequence,
                epoch=1,
                received_at=float(sequence),
            )
        except (ValueError, struct.error) as exc:
            failures += 1
            if len(reasons) < 5:
                reasons.append(f"decode failure: {exc}")
            continue
        samples.append(sample)
        ok, sample_reasons = _is_plausible(
            sample,
            max_abs_position_mm=max_abs_position_mm,
            max_abs_velocity_mm_s=max_abs_velocity_mm_s,
            max_abs_acceleration_mm_s2=max_abs_acceleration_mm_s2,
            max_abs_force=max_abs_force,
        )
        if ok:
            plausible += 1
            plausible_samples.append(sample)
        else:
            implausible += 1
            for reason in sample_reasons:
                if reason not in reasons and len(reasons) < 5:
                    reasons.append(reason)

    means: dict[str, Optional[float]] = {"x": None, "y": None, "z": None}
    error_max_mean: Optional[float] = None
    error_p95: Optional[float] = None
    collision_frames = sum(1 for sample in samples if sample.has_collision)

    position_errors: list[float] = []
    # Statistics are computed only from plausible samples. For a real motion
    # capture the early frames legitimately start far from the commanded final
    # pose, so endian confirmation evaluates a bounded tail window rather than
    # averaging the entire trajectory. Wrong-endian finite doubles can also be
    # astronomically large and overflow fsum.
    tail_count = min(20, len(plausible_samples))
    evaluation_samples = plausible_samples[-tail_count:] if tail_count else []
    if evaluation_samples:
        for axis in ("x", "y", "z"):
            means[axis] = statistics.fmean(
                sample.position[axis] for sample in evaluation_samples
            )
        if expected_pose is not None:
            expected = expected_pose.as_dict()
            position_errors = [
                max(abs(sample.position[axis] - expected[axis]) for axis in ("x", "y", "z"))
                for sample in evaluation_samples
            ]
            error_max_mean = statistics.fmean(position_errors)
            error_p95 = percentile(position_errors, 95.0)

    decoded = len(samples)
    score = float(failures * 1_000_000 + implausible * 100_000)
    if expected_pose is not None and error_max_mean is not None:
        divisor = max(position_tolerance_mm, 1e-12)
        score += error_max_mean / divisor
    else:
        # Without a known pose the tool must remain conservative. Plausibility
        # can reject an endian, but cannot by itself certify the other endian.
        score += 10_000.0
        reasons.append("known expected pose not supplied; confirmation is restricted")

    if decoded == 0:
        score += 10_000_000.0
        reasons.append("no frames decoded")

    return EndianScore(
        endian=endian,
        label=endian_name(endian),
        decoded_frames=decoded,
        decode_failures=failures,
        plausible_frames=plausible,
        implausible_frames=implausible,
        evaluated_tail_frames=len(evaluation_samples),
        mean_position=means,
        position_error_max_mean_mm=error_max_mean,
        position_error_p95_mm=error_p95,
        collision_frames=collision_frames,
        score=score,
        reasons=tuple(dict.fromkeys(reasons)),
    )


def load_chunks(capture_dir: Path) -> list[dict[str, object]]:
    path = capture_dir / "chunks.jsonl"
    if not path.exists():
        return []
    chunks: list[dict[str, object]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid chunks.jsonl line {line_number}: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"chunks.jsonl line {line_number} must be an object")
        chunks.append(value)
    return chunks


def timing_metrics(chunks: Sequence[dict[str, object]], *, total_bytes: int) -> TimingMetrics:
    sizes = [int(chunk.get("bytes", 0)) for chunk in chunks]
    times = [float(chunk["monotonic_s"]) for chunk in chunks if "monotonic_s" in chunk]
    emitted = [int(chunk.get("complete_frames_after_chunk", 0)) for chunk in chunks]
    complete_frames = total_bytes // NX_FEEDBACK_FRAME_BYTES
    remainder = total_bytes % NX_FEEDBACK_FRAME_BYTES
    duration = None
    frame_rate = None
    if len(times) >= 2 and times[-1] > times[0]:
        duration = times[-1] - times[0]
        frame_rate = complete_frames / duration
    inter_ms = [
        (later - earlier) * 1000.0
        for earlier, later in zip(times, times[1:])
        if later >= earlier
    ]
    return TimingMetrics(
        chunk_count=len(chunks),
        total_bytes=total_bytes,
        complete_frames=complete_frames,
        remainder_bytes=remainder,
        capture_duration_s=duration,
        average_frame_rate_hz=frame_rate,
        mean_chunk_bytes=statistics.fmean(sizes) if sizes else None,
        median_chunk_bytes=statistics.median(sizes) if sizes else None,
        p95_chunk_bytes=percentile(sizes, 95.0),
        mean_inter_chunk_ms=statistics.fmean(inter_ms) if inter_ms else None,
        median_inter_chunk_ms=statistics.median(inter_ms) if inter_ms else None,
        p95_inter_chunk_ms=percentile(inter_ms, 95.0),
        chunks_with_multiple_frames=sum(1 for value in emitted if value > 1),
    )


def _write_frames_csv(path: Path, frames: Sequence[bytes], *, endian: str) -> None:
    fieldnames = [
        "frame_index",
        "sp_x",
        "sv_x",
        "sa_x",
        "sp_y",
        "sv_y",
        "sa_y",
        "sp_z",
        "sv_z",
        "sa_z",
        "sf_x",
        "sf_y",
        "sf_z",
        "status_0",
        "status_1",
        "status_2",
        "status_3",
        "status_bytes_hex",
        "collision_mask",
        "collision_mapping_verified",
        "unmapped_status_active",
        "collision_x",
        "collision_y",
        "collision_z",
        "collision_tool",
        "raw_sha256",
        "decode_error",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for index, frame in enumerate(frames, start=1):
            row: dict[str, object] = {"frame_index": index, "decode_error": ""}
            try:
                sample = decode_nx_feedback_frame(frame, endian=endian, rx_seq=index, epoch=1)
                row.update(
                    {
                        "sp_x": sample.position["x"],
                        "sv_x": sample.velocity["x"],
                        "sa_x": sample.acceleration["x"],
                        "sp_y": sample.position["y"],
                        "sv_y": sample.velocity["y"],
                        "sa_y": sample.acceleration["y"],
                        "sp_z": sample.position["z"],
                        "sv_z": sample.velocity["z"],
                        "sa_z": sample.acceleration["z"],
                        "sf_x": sample.force["x"],
                        "sf_y": sample.force["y"],
                        "sf_z": sample.force["z"],
                        "status_0": sample.status_bytes[0],
                        "status_1": sample.status_bytes[1],
                        "status_2": sample.status_bytes[2],
                        "status_3": sample.status_bytes[3],
                        "status_bytes_hex": sample.status_bytes_hex,
                        "collision_mask": sample.collision_mask,
                        "collision_mapping_verified": sample.collision_mapping_verified,
                        "unmapped_status_active": sample.unmapped_status_active,
                        "collision_x": sample.collision["x"],
                        "collision_y": sample.collision["y"],
                        "collision_z": sample.collision["z"],
                        "collision_tool": sample.collision["tool"],
                        "raw_sha256": sample.raw_sha256,
                    }
                )
            except Exception as exc:  # capture evidence, do not hide failure
                row["decode_error"] = str(exc)
            writer.writerow(row)


def choose_verdict(
    big: EndianScore,
    little: EndianScore,
    *,
    expected_pose: Optional[ExpectedPose],
    position_tolerance_mm: float,
    score_margin: float,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if big.decoded_frames == 0 and little.decoded_frames == 0:
        return VERDICT_INVALID, ["neither endian decoded a frame"]
    if expected_pose is None:
        return VERDICT_AMBIGUOUS, ["expected pose is required for a positive endian confirmation"]

    candidates = sorted((big, little), key=lambda score: score.score)
    best, other = candidates
    best_error = best.position_error_p95_mm
    if best_error is None or best_error > position_tolerance_mm:
        reasons.append(
            "best endian does not match expected pose within configured p95 tolerance"
        )
        return VERDICT_AMBIGUOUS, reasons
    if best.plausible_frames == 0:
        return VERDICT_AMBIGUOUS, ["best endian has no plausible frames"]
    if other.score - best.score < score_margin:
        reasons.append("big/little scores are too close for fail-safe confirmation")
        return VERDICT_AMBIGUOUS, reasons

    verdict = VERDICT_CONFIRMED_BIG if best.endian == ">" else VERDICT_CONFIRMED_LITTLE
    reasons.append(
        f"{best.label} endian matches expected pose and exceeds score margin"
    )
    return verdict, reasons


def analyze_capture(
    capture_dir: Path,
    *,
    expected_pose: Optional[ExpectedPose],
    position_tolerance_mm: float = 0.5,
    score_margin: float = 10.0,
    max_abs_position_mm: float = 100_000.0,
    max_abs_velocity_mm_s: float = 100_000.0,
    max_abs_acceleration_mm_s2: float = 1_000_000.0,
    max_abs_force: float = 1_000_000_000.0,
) -> dict[str, object]:
    capture_dir = Path(capture_dir)
    raw_path = capture_dir / "raw_stream.bin"
    if not raw_path.exists():
        report = {
            "schema_version": 1,
            "generated_at": utc_now_iso(),
            "capture_dir": str(capture_dir),
            "verdict": VERDICT_NO_DATA,
            "reasons": ["raw_stream.bin not found"],
            "evidence_level": "L0",
        }
        write_analysis_report(capture_dir, report)
        return report

    raw = raw_path.read_bytes()
    frames, remainder = split_feedback_frames(raw)
    chunks = load_chunks(capture_dir)
    timing = timing_metrics(chunks, total_bytes=len(raw))

    if not frames:
        report = {
            "schema_version": 1,
            "generated_at": utc_now_iso(),
            "capture_dir": str(capture_dir),
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "verdict": VERDICT_NO_DATA,
            "reasons": ["capture contains no complete 100-byte feedback frame"],
            "timing": timing.as_dict(),
            "evidence_level": "L0",
        }
        write_analysis_report(capture_dir, report)
        return report

    common = {
        "frames": frames,
        "expected_pose": expected_pose,
        "position_tolerance_mm": position_tolerance_mm,
        "max_abs_position_mm": max_abs_position_mm,
        "max_abs_velocity_mm_s": max_abs_velocity_mm_s,
        "max_abs_acceleration_mm_s2": max_abs_acceleration_mm_s2,
        "max_abs_force": max_abs_force,
    }
    big = score_endian(endian=">", **common)
    little = score_endian(endian="<", **common)
    verdict, verdict_reasons = choose_verdict(
        big,
        little,
        expected_pose=expected_pose,
        position_tolerance_mm=position_tolerance_mm,
        score_margin=score_margin,
    )

    _write_frames_csv(capture_dir / "frames_big_endian.csv", frames, endian=">")
    _write_frames_csv(capture_dir / "frames_little_endian.csv", frames, endian="<")

    report = {
        "schema_version": 1,
        "generated_at": utc_now_iso(),
        "capture_dir": str(capture_dir),
        "raw_bytes": len(raw),
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "complete_frames": len(frames),
        "remainder_bytes": len(remainder),
        "remainder_sha256": hashlib.sha256(remainder).hexdigest() if remainder else None,
        "expected_pose": None if expected_pose is None else expected_pose.as_dict(),
        "position_tolerance_mm": position_tolerance_mm,
        "score_margin": score_margin,
        "big_endian": big.as_dict(),
        "little_endian": little.as_dict(),
        "timing": timing.as_dict(),
        "verdict": verdict,
        "reasons": verdict_reasons,
        "evidence_level": "L4_CANDIDATE" if verdict.startswith("CONFIRMED") else "L4_INCOMPLETE",
        "limitations": [
            "average frame rate is measured at the TCP application receiver, not inside the NX solver",
            "TCP recv chunk boundaries are not frame boundaries",
            "the exact collision mapping of trailing bytes 96..99 requires one-signal-at-a-time real NX captures",
            "a confirmed endian still requires operator review of decoded signals and NX setup",
        ],
    }
    write_analysis_report(capture_dir, report)
    return report


def write_analysis_report(capture_dir: Path, report: dict[str, object]) -> None:
    capture_dir.mkdir(parents=True, exist_ok=True)
    (capture_dir / "analysis_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    lines = [
        "# NX MCD T04 Calibration Report",
        "",
        f"- Generated: `{report.get('generated_at')}`",
        f"- Verdict: **{report.get('verdict')}**",
        f"- Evidence: `{report.get('evidence_level')}`",
        f"- Raw bytes: `{report.get('raw_bytes', 0)}`",
        f"- Complete 100-byte frames: `{report.get('complete_frames', 0)}`",
        f"- Remainder bytes: `{report.get('remainder_bytes', 0)}`",
        "",
        "## Reasons",
    ]
    for reason in report.get("reasons", []):
        lines.append(f"- {reason}")
    lines += [
        "",
        "## Timing",
        "",
        "```json",
        json.dumps(report.get("timing", {}), indent=2, ensure_ascii=False),
        "```",
        "",
        "## Big-endian score",
        "",
        "```json",
        json.dumps(report.get("big_endian", {}), indent=2, ensure_ascii=False),
        "```",
        "",
        "## Little-endian score",
        "",
        "```json",
        json.dumps(report.get("little_endian", {}), indent=2, ensure_ascii=False),
        "```",
        "",
        "## Limitations",
    ]
    for item in report.get("limitations", []):
        lines.append(f"- {item}")
    (capture_dir / "analysis_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_capture(args: argparse.Namespace) -> int:
    host = str(args.host)
    if host not in {"127.0.0.1", "localhost", "::1"} and not args.allow_non_loopback:
        raise SystemExit(
            "Refusing non-loopback bind. Use --allow-non-loopback only after an explicit network review."
        )

    output_root = Path(args.output_dir)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    capture_dir = output_root / f"nx_t04_{stamp}"
    capture_dir.mkdir(parents=True, exist_ok=False)

    expected = ExpectedPose(args.cp_x, args.cp_y, args.cp_z)
    send_endian = validate_endian_label(args.send_endian)
    command_frame = pack_command_frame(
        endian=send_endian,
        cp=expected,
        velocity_mm_s=args.velocity,
        acceleration_mm_s2=args.acceleration,
        deceleration_mm_s2=args.deceleration,
    )
    manifest = {
        "schema_version": 1,
        "created_at": utc_now_iso(),
        "host": host,
        "port": args.port,
        "duration_s": args.duration,
        "send_hz": args.send_hz,
        "send_endian": endian_name(send_endian),
        "command_frame_bytes": len(command_frame),
        "expected_pose": expected.as_dict(),
        "velocity_mm_s": args.velocity,
        "acceleration_mm_s2": args.acceleration,
        "deceleration_mm_s2": args.deceleration,
        "physical_machine_connection": False,
        "fluidnc_connection": False,
        "note": "Standalone NX MCD virtual-model calibration server only.",
    }
    (capture_dir / "capture_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    raw_path = capture_dir / "raw_stream.bin"
    chunks_path = capture_dir / "chunks.jsonl"
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, args.port))
    server.listen(1)
    server.settimeout(args.accept_timeout)
    print(f"[T04] Listening for NX MCD on {host}:{args.port}")
    print("[T04] Stop edge_backend/main.py first; only one server may own port 6001.")
    print(f"[T04] Capture output: {capture_dir}")

    conn: Optional[socket.socket] = None
    start = time.monotonic()
    frame_buffered = 0
    chunk_index = 0
    collision_latched = 0
    try:
        conn, addr = server.accept()
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        conn.setblocking(False)
        print(f"[T04] NX connected from {addr}")
        deadline = time.monotonic() + args.duration
        next_send = time.monotonic()
        with raw_path.open("wb") as raw_handle, chunks_path.open("w", encoding="utf-8") as chunks_handle:
            while time.monotonic() < deadline:
                now = time.monotonic()
                if now >= next_send:
                    try:
                        conn.sendall(command_frame)
                    except BlockingIOError:
                        # Non-blocking socket backpressure is transient. The
                        # next loop retries without duplicating a queued frame.
                        pass
                    next_send = now + (1.0 / max(args.send_hz, 1.0))

                readable, _, exceptional = select.select([conn], [], [conn], 0.02)
                if exceptional:
                    raise ConnectionError("NX socket exceptional condition")
                if conn in readable:
                    chunk = conn.recv(65536)
                    if not chunk:
                        print("[T04] NX disconnected")
                        break
                    received_at = time.monotonic()
                    raw_handle.write(chunk)
                    raw_handle.flush()
                    chunk_index += 1
                    before_frames = frame_buffered // NX_FEEDBACK_FRAME_BYTES
                    frame_buffered += len(chunk)
                    after_frames = frame_buffered // NX_FEEDBACK_FRAME_BYTES
                    complete_after_chunk = after_frames - before_frames
                    frame_buffered %= NX_FEEDBACK_FRAME_BYTES

                    # Collision byte is endian-independent. Inspect only complete
                    # aligned frames from the cumulative raw stream after capture
                    # analysis; live stop is intentionally not attempted here to
                    # avoid making safety decisions from a partially aligned buffer.
                    record = {
                        "chunk_index": chunk_index,
                        "wall_time_utc": utc_now_iso(),
                        "monotonic_s": received_at,
                        "bytes": len(chunk),
                        "sha256": hashlib.sha256(chunk).hexdigest(),
                        "hex_prefix": chunk[:32].hex(),
                        "complete_frames_after_chunk": complete_after_chunk,
                        "buffered_remainder_after_chunk": frame_buffered,
                    }
                    chunks_handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                    chunks_handle.flush()
        elapsed = time.monotonic() - start
        captured_raw = raw_path.read_bytes() if raw_path.exists() else b""
        captured_frames, _ = split_feedback_frames(captured_raw)
        collision_latched = 0
        for captured_frame in captured_frames:
            collision_latched |= int(captured_frame[96]) & COLLISION_ALLOWED_MASK
        manifest["completed_at"] = utc_now_iso()
        manifest["elapsed_s"] = elapsed
        manifest["chunks"] = chunk_index
        manifest["collision_latched"] = collision_latched
        (capture_dir / "capture_manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    finally:
        if conn is not None:
            try:
                conn.close()
            except OSError:
                pass
        server.close()

    report = analyze_capture(
        capture_dir,
        expected_pose=expected,
        position_tolerance_mm=args.position_tolerance,
        score_margin=args.score_margin,
        max_abs_position_mm=args.max_abs_position,
        max_abs_velocity_mm_s=args.max_abs_velocity,
        max_abs_acceleration_mm_s2=args.max_abs_acceleration,
        max_abs_force=args.max_abs_force,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"[T04] Verdict: {report['verdict']}")
    return 0 if str(report["verdict"]).startswith("CONFIRMED") else 2


def run_analyze(args: argparse.Namespace) -> int:
    expected = None
    if args.expected_x is not None or args.expected_y is not None or args.expected_z is not None:
        if None in (args.expected_x, args.expected_y, args.expected_z):
            raise SystemExit("expected-x, expected-y and expected-z must be supplied together")
        expected = ExpectedPose(args.expected_x, args.expected_y, args.expected_z)
    report = analyze_capture(
        Path(args.capture_dir),
        expected_pose=expected,
        position_tolerance_mm=args.position_tolerance,
        score_margin=args.score_margin,
        max_abs_position_mm=args.max_abs_position,
        max_abs_velocity_mm_s=args.max_abs_velocity,
        max_abs_acceleration_mm_s2=args.max_abs_acceleration,
        max_abs_force=args.max_abs_force,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if str(report["verdict"]).startswith("CONFIRMED") else 2


def run_fixture(args: argparse.Namespace) -> int:
    """Generate a synthetic capture for L2 tooling tests only."""

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    endian = validate_endian_label(args.endian)
    expected = ExpectedPose(args.x, args.y, args.z)
    frames: list[bytes] = []
    for index in range(args.frames):
        jitter = (index % 3 - 1) * args.jitter
        values = (
            expected.x + jitter,
            0.0,
            0.0,
            expected.y - jitter,
            0.0,
            0.0,
            expected.z + jitter,
            0.0,
            0.0,
            1.0,
            2.0,
            3.0,
        )
        frames.append(struct.pack(endian + "12d4B", *values, args.collision_mask, 0, 0, 0))
    raw = b"".join(frames)
    (output / "raw_stream.bin").write_bytes(raw)

    chunk_sizes = [1, 17, 79, 194, 53]
    offset = 0
    chunks: list[dict[str, object]] = []
    mono = 100.0
    buffer_remainder = 0
    chunk_index = 0
    while offset < len(raw):
        size = chunk_sizes[chunk_index % len(chunk_sizes)]
        chunk = raw[offset : offset + size]
        offset += len(chunk)
        chunk_index += 1
        mono += 0.033
        before = buffer_remainder // NX_FEEDBACK_FRAME_BYTES
        buffer_remainder += len(chunk)
        after = buffer_remainder // NX_FEEDBACK_FRAME_BYTES
        emitted = after - before
        buffer_remainder %= NX_FEEDBACK_FRAME_BYTES
        chunks.append(
            {
                "chunk_index": chunk_index,
                "wall_time_utc": utc_now_iso(),
                "monotonic_s": mono,
                "bytes": len(chunk),
                "sha256": hashlib.sha256(chunk).hexdigest(),
                "hex_prefix": chunk[:32].hex(),
                "complete_frames_after_chunk": emitted,
                "buffered_remainder_after_chunk": buffer_remainder,
            }
        )
    (output / "chunks.jsonl").write_text(
        "".join(json.dumps(chunk) + "\n" for chunk in chunks), encoding="utf-8"
    )
    (output / "capture_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "synthetic": True,
                "endian": endian_name(endian),
                "expected_pose": expected.as_dict(),
                "frames": args.frames,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    report = analyze_capture(
        output,
        expected_pose=expected,
        position_tolerance_mm=args.position_tolerance,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if str(report["verdict"]).startswith("CONFIRMED") else 2


def add_analysis_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--position-tolerance", type=float, default=0.5)
    parser.add_argument("--score-margin", type=float, default=10.0)
    parser.add_argument("--max-abs-position", type=float, default=100_000.0)
    parser.add_argument("--max-abs-velocity", type=float, default=100_000.0)
    parser.add_argument("--max-abs-acceleration", type=float, default=1_000_000.0)
    parser.add_argument("--max-abs-force", type=float, default=1_000_000_000.0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    capture = sub.add_parser("capture", help="run a one-shot real NX MCD capture")
    capture.add_argument("--host", default="127.0.0.1")
    capture.add_argument("--port", type=int, default=6001)
    capture.add_argument("--allow-non-loopback", action="store_true")
    capture.add_argument("--accept-timeout", type=float, default=120.0)
    capture.add_argument("--duration", type=float, default=15.0)
    capture.add_argument("--send-hz", type=float, default=30.0)
    capture.add_argument("--send-endian", default="big")
    capture.add_argument("--cp-x", type=float, required=True)
    capture.add_argument("--cp-y", type=float, required=True)
    capture.add_argument("--cp-z", type=float, required=True)
    capture.add_argument("--velocity", type=float, default=1.0)
    capture.add_argument("--acceleration", type=float, default=1.0)
    capture.add_argument("--deceleration", type=float, default=1.0)
    capture.add_argument(
        "--output-dir", default="reports/mission11_v2_t04_nx_calibration"
    )
    add_analysis_args(capture)
    capture.set_defaults(func=run_capture)

    analyze = sub.add_parser("analyze", help="analyze an existing capture directory")
    analyze.add_argument("capture_dir")
    analyze.add_argument("--expected-x", type=float)
    analyze.add_argument("--expected-y", type=float)
    analyze.add_argument("--expected-z", type=float)
    add_analysis_args(analyze)
    analyze.set_defaults(func=run_analyze)

    fixture = sub.add_parser("fixture", help="generate a synthetic L2 fixture")
    fixture.add_argument("--output-dir", required=True)
    fixture.add_argument("--endian", default="big")
    fixture.add_argument("--x", type=float, default=10.0)
    fixture.add_argument("--y", type=float, default=20.0)
    fixture.add_argument("--z", type=float, default=30.0)
    fixture.add_argument("--frames", type=int, default=30)
    fixture.add_argument("--jitter", type=float, default=0.01)
    fixture.add_argument("--collision-mask", type=int, default=0)
    fixture.add_argument("--position-tolerance", type=float, default=0.5)
    fixture.set_defaults(func=run_fixture)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
