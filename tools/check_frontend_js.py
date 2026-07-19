#!/usr/bin/env python3
"""Stable Windows/Linux frontend JavaScript syntax checker.

Parses every file explicitly as an ES module using `node --input-type=module --check`
through stdin. This catches module-only syntax failures that plain `node --check file.js`
can miss. This prevents native stderr from being promoted to
NativeCommandError and gives a deterministic exit code for RUN_00_LOCAL_VERIFY.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def _configure_utf8_stdio() -> None:
    """Make captured pytest/subprocess output safe on Windows cp1252 consoles."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        # Some redirected streams may not expose reconfigure(); the subprocess
        # calls below still use encoding="utf-8", errors="replace".
        pass


def main() -> int:
    _configure_utf8_stdio()

    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default="frontend/js", help="Directory containing .js files")
    parser.add_argument(
        "--node-exe",
        default=os.environ.get("NODE_EXE", "node"),
        help="Node executable path/name; defaults to NODE_EXE or node",
    )
    args = parser.parse_args()

    js_dir = Path(args.dir)
    node_exe = args.node_exe

    files = sorted(js_dir.glob("*.js"))
    if not files:
        print(f"No JS files found in {js_dir}")
        return 0

    failed = 0
    for js_file in files:
        source = js_file.read_text(encoding="utf-8")
        proc = subprocess.run(
            [node_exe, "--input-type=module", "--check"],
            input=source,
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode == 0:
            print(f"PASS {js_file}")
        else:
            failed += 1
            print(f"FAIL {js_file}")
            if proc.stdout:
                print(proc.stdout.rstrip())
            if proc.stderr:
                print(proc.stderr.rstrip())

    print(f"Checked {len(files)} JS files; failed={failed}")
    if failed:
        print("NODE CHECK FAIL")
    else:
        print("NODE CHECK PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())