"""Mission 04+ axis 1D driver-motor reference model.

This module is a sandbox-safe reference for the detailed per-axis subsystem shown
in the user's Simulink screenshot:

    step/dir -> pulse expansion -> driver current/torque -> motor/load -> x,v,a

It is intentionally dependency-free and deterministic so it can be tested in a
clean environment. The MATLAB/Simulink implementation can use the same contract:
input step pulses + direction + reset, output position/velocity/acceleration and
diagnostic current/torque.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import csv
import json
import math
from typing import Iterable, List, Dict


@dataclass(frozen=True)
class Axis1DConfig:
    axis: str = "X"
    sample_s: float = 1.0e-4
    steps_per_mm: float = 200.0
    max_accel_mms2: float = 2500.0
    stiffness_s2: float = 900.0       # command-position tracking stiffness
    damping_s: float = 60.0           # velocity damping
    driver_current_a: float = 2.0
    torque_constant_nm_per_a: float = 0.45
    screw_pitch_mm: float = 5.0
    table_mass_kg: float = 2.5
    viscous_damping_n_s_per_m: float = 8.0

    def validate(self) -> None:
        if self.sample_s <= 0:
            raise ValueError("sample_s must be positive")
        if self.steps_per_mm <= 0:
            raise ValueError("steps_per_mm must be positive")
        if self.max_accel_mms2 <= 0:
            raise ValueError("max_accel_mms2 must be positive")
        if self.driver_current_a < 0:
            raise ValueError("driver_current_a must be non-negative")
        if self.torque_constant_nm_per_a < 0:
            raise ValueError("torque_constant_nm_per_a must be non-negative")


@dataclass
class Axis1DSample:
    t_s: float
    axis: str
    command_step: int
    command_mm: float
    position_mm: float
    velocity_mms: float
    acceleration_mms2: float
    current_a: float
    current_b: float
    torque_nm: float
    step_pulse: int
    dir_negative: int
    reset: int


class Axis1DDriverMotor:
    """Open-loop step/dir driven 1D axis model.

    The stepper command position is derived from step pulses. The simulated load
    follows that command through a bounded second-order model. This is a safe
    engineering approximation for evidence/benchmarking and a contract for the
    later Simulink subsystem; it is not a substitute for a calibrated Simscape or
    measured motor/driver model.
    """

    def __init__(self, config: Axis1DConfig) -> None:
        config.validate()
        self.cfg = config
        self.reset_state()

    def reset_state(self) -> None:
        self.t_s = 0.0
        self.command_step = 0
        self.position_mm = 0.0
        self.velocity_mms = 0.0
        self.acceleration_mms2 = 0.0

    def step(self, step_pulse: bool, dir_negative: bool = False, reset: bool = False) -> Axis1DSample:
        if reset:
            self.reset_state()

        if step_pulse and not reset:
            self.command_step += -1 if dir_negative else 1

        cmd_mm = self.command_step / self.cfg.steps_per_mm
        error_mm = cmd_mm - self.position_mm
        a_cmd = self.cfg.stiffness_s2 * error_mm - self.cfg.damping_s * self.velocity_mms
        a_cmd = max(-self.cfg.max_accel_mms2, min(self.cfg.max_accel_mms2, a_cmd))

        self.acceleration_mms2 = a_cmd
        self.velocity_mms += self.acceleration_mms2 * self.cfg.sample_s
        self.position_mm += self.velocity_mms * self.cfg.sample_s

        # Diagnostic pseudo phase currents from commanded electrical angle.
        # Four full-step states per motor revolution are approximated as a sine/cosine pair.
        electrical_angle = 2.0 * math.pi * (self.command_step % 4) / 4.0
        current_a = self.cfg.driver_current_a * math.sin(electrical_angle)
        current_b = self.cfg.driver_current_a * math.cos(electrical_angle)
        torque_nm = self.cfg.torque_constant_nm_per_a * math.hypot(current_a, current_b)

        sample = Axis1DSample(
            t_s=self.t_s,
            axis=self.cfg.axis,
            command_step=self.command_step,
            command_mm=cmd_mm,
            position_mm=self.position_mm,
            velocity_mms=self.velocity_mms,
            acceleration_mms2=self.acceleration_mms2,
            current_a=current_a,
            current_b=current_b,
            torque_nm=torque_nm,
            step_pulse=int(bool(step_pulse)),
            dir_negative=int(bool(dir_negative)),
            reset=int(bool(reset)),
        )
        self.t_s += self.cfg.sample_s
        return sample


def trapezoid_pulse_train(target_mm: float, cfg: Axis1DConfig, pulse_period_samples: int = 8, settle_samples: int = 5000) -> Iterable[tuple[bool, bool, bool]]:
    """Generate a simple deterministic pulse train toward a target position."""
    total_steps = int(round(abs(target_mm) * cfg.steps_per_mm))
    dir_negative = target_mm < 0
    for _ in range(total_steps):
        yield True, dir_negative, False
        for _ in range(max(0, pulse_period_samples - 1)):
            yield False, dir_negative, False
    for _ in range(settle_samples):
        yield False, dir_negative, False


def run_axis_case(target_mm: float, cfg: Axis1DConfig) -> List[Axis1DSample]:
    model = Axis1DDriverMotor(cfg)
    samples: List[Axis1DSample] = []
    for step_pulse, dir_negative, reset in trapezoid_pulse_train(target_mm, cfg):
        samples.append(model.step(step_pulse, dir_negative, reset))
    return samples


def summarize_case(name: str, target_mm: float, samples: List[Axis1DSample]) -> Dict[str, float | str]:
    final = samples[-1]
    errors = [s.command_mm - s.position_mm for s in samples]
    endpoint_error = target_mm - final.position_mm
    rms_tracking_error = math.sqrt(sum(e * e for e in errors) / len(errors))
    max_abs_tracking_error = max(abs(e) for e in errors)
    return {
        "case": name,
        "axis": final.axis,
        "target_mm": target_mm,
        "command_mm": final.command_mm,
        "final_position_mm": final.position_mm,
        "endpoint_error_mm": endpoint_error,
        "rms_tracking_error_mm": rms_tracking_error,
        "max_abs_tracking_error_mm": max_abs_tracking_error,
        "max_velocity_mms": max(abs(s.velocity_mms) for s in samples),
        "max_acceleration_mms2": max(abs(s.acceleration_mms2) for s in samples),
        "samples": len(samples),
        "status": "PASS" if abs(endpoint_error) <= 0.05 else "FAIL",
    }


def write_samples_csv(path: Path, samples: List[Axis1DSample]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(samples[0]).keys()))
        writer.writeheader()
        for sample in samples:
            writer.writerow(asdict(sample))


def run_selftest(out_dir: Path) -> Dict[str, object]:
    out_dir.mkdir(parents=True, exist_ok=True)
    cases = [
        ("x_positive_10mm", 10.0, Axis1DConfig(axis="X")),
        ("y_positive_5mm", 5.0, Axis1DConfig(axis="Y")),
        ("z_negative_2mm", -2.0, Axis1DConfig(axis="Z")),
    ]
    rows = []
    for case_name, target_mm, cfg in cases:
        samples = run_axis_case(target_mm, cfg)
        write_samples_csv(out_dir / f"{case_name}_samples.csv", samples)
        rows.append(summarize_case(case_name, target_mm, samples))

    summary_path = out_dir / "axis1d_driver_motor_summary.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    payload = {
        "status": "PASS" if all(r["status"] == "PASS" for r in rows) else "FAIL",
        "rows": rows,
        "summary_csv": str(summary_path),
        "note": "Sandbox reference model only. MATLAB/NX real verification remains separate.",
    }
    (out_dir / "axis1d_driver_motor_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run Mission 04+ axis 1D driver-motor reference self-test.")
    parser.add_argument("--out", default="reports/mission4_axis1d", help="Output directory for CSV/JSON results")
    args = parser.parse_args()

    result = run_selftest(Path(args.out))
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["status"] == "PASS" else 1)
