"""Run every integration test file in a fresh process and aggregate evidence.

File-level isolation prevents a background thread from one legacy integration
test from hiding the exit status of all other tests.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys


def _count_tests(output: str) -> int:
    patterns = (
        r"(\d+) passed",
        r"(\d+) failed",
        r"(\d+) error",
        r"(\d+) skipped",
    )
    counts = [int(m.group(1)) for p in patterns for m in [re.search(p, output)] if m]
    return sum(counts)


def run(root: Path, out: Path, timeout_s: int) -> dict:
    files = sorted((root / "integration_tests").glob("test_*.py"))
    results = []
    for index, path in enumerate(files, start=1):
        rel = path.relative_to(root).as_posix()
        print(f"[{index}/{len(files)}] {rel}", flush=True)
        proc = subprocess.Popen(
            [sys.executable, "tools/pytest_force_exit.py", "-q", rel],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        timed_out = False
        try:
            output, _ = proc.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(proc.pid, signal.SIGKILL)
            output, _ = proc.communicate()
            output += "\nFILE_TEST_TIMEOUT"
        results.append({
            "file": rel,
            "passed": proc.returncode == 0 and not timed_out,
            "exit_code": proc.returncode,
            "timed_out": timed_out,
            "test_count": _count_tests(output),
            "output_tail": "\n".join(output.splitlines()[-25:]),
        })
    payload = {
        "schema": "mission23.3-isolated-full-regression-v1",
        "files": len(results),
        "files_passed": sum(item["passed"] for item in results),
        "files_failed": sum(not item["passed"] for item in results),
        "tests_observed": sum(item["test_count"] for item in results),
        "complete": all(item["passed"] for item in results),
        "results": results,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("files", "files_passed", "files_failed", "tests_observed", "complete")}), flush=True)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=45)
    args = parser.parse_args()
    payload = run(args.root.resolve(), args.out.resolve(), args.timeout)
    return 0 if payload["complete"] else 2


if __name__ == "__main__":
    code = main()
    try:
        sys.stdout.flush(); sys.stderr.flush()
    finally:
        os._exit(code)
