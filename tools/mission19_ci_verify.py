#!/usr/bin/env python3
"""Project-local CI verifier for the CNC repository.

This is intentionally vendor-neutral: it can run in GitHub Actions, GitLab CI,
Jenkins, a local shell, or another runner.  It never connects to FluidNC or
issues machine commands.
"""

from __future__ import annotations

import argparse
import compileall
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def scan_matlab_literal_newlines() -> list[str]:
    """Detect MATLAB fprintf/warning character vectors split by a real newline."""
    bad: list[str] = []
    for path in ROOT.rglob("*.m"):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception as exc:
            bad.append(f"{path.relative_to(ROOT)}: unreadable: {exc}")
            continue
        for lineno, line in enumerate(lines, 1):
            if "fprintf(" not in line and "warning(" not in line:
                continue
            quote_count = len(line.replace("''", "").split("'")) - 1
            if quote_count % 2:
                bad.append(f"{path.relative_to(ROOT)}:{lineno}")
    return bad


def run(cmd: list[str]) -> int:
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=ROOT, check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-pytest", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []

    if not compileall.compile_dir(ROOT / "cloud_backend", quiet=1):
        failures.append("cloud_backend compileall")
    if not compileall.compile_dir(ROOT / "edge_backend", quiet=1):
        failures.append("edge_backend compileall")

    matlab_bad = scan_matlab_literal_newlines()
    if matlab_bad:
        failures.append("MATLAB literal newline: " + ", ".join(matlab_bad))

    js_files = sorted((ROOT / "frontend" / "js").glob("*.js"))
    for path in js_files:
        if run(["node", "--check", str(path)]) != 0:
            failures.append(f"node --check {path.relative_to(ROOT)}")

    if not args.skip_pytest:
        if run([sys.executable, "-m", "pytest", "-q", "integration_tests"]) != 0:
            failures.append("pytest integration_tests")

    if failures:
        print("FAIL")
        for item in failures:
            print(" -", item)
        return 1

    print("PASS: compileall + JS syntax + MATLAB literal-newline guard + pytest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
