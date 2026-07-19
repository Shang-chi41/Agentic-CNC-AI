#!/usr/bin/env python3
"""Static/sandbox verifier for the three operator-confirmed CNC flows."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--out", default="reports/mission20_three_flow_verification.json")
    args = parser.parse_args()
    root = Path(args.project_root).resolve()
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "integration_tests/test_mission20_three_flow_contract.py",
    ]
    proc = subprocess.run(cmd, cwd=root, text=True, capture_output=True)
    payload = {
        "command": " ".join(cmd),
        "working_directory": str(root),
        "exit_code": proc.returncode,
        "result": "PASS" if proc.returncode == 0 else "FAIL",
        "evidence_level": "L2",
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "flows": {
            "check": "MATLAB CHECK telemetry -> Edge selector -> NX MCD; no FluidNC execution",
            "run": "Exact approved artifact fanout to MATLAB and FluidNC; only FluidNC actual MPos drives NX",
            "jog": "FluidNC WebUI originates JOG; Edge passively mirrors actual MPos to NX",
        },
    }
    out = root / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, file=sys.stderr, end="")
    print(f"Mission20 three-flow verification: {payload['result']} -> {out}")
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
