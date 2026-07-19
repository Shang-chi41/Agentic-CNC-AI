#!/usr/bin/env python3
"""One-command static/sandbox verification for Mission 11 V2.

No FluidNC socket, MATLAB bridge, NX MCD runtime, or physical machine command is
issued.  The verifier temporarily installs a deterministic fail-closed .env,
records every command, and restores the previous .env atomically.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "agentic_execution_kit" / "MISSION_11_V2_STATIC_RUNTIME" / "EVIDENCE" / "STATIC" / "latest"


def _safe_env_text() -> str:
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    safe = {
        "MONGO_URI": "mongodb://127.0.0.1:27017/cnc_db",
        "JWT_SECRET": "PACKAGE_SAFE_TEST_ONLY_JWT_SECRET",
        "SYNC_API_KEY": "PACKAGE_SAFE_TEST_ONLY_SYNC_KEY",
        "FCC_AUTH_TOKEN": "fcc-no-auth",
        "GEMINI_API_KEY": "NOT_CONFIGURED",
        "ANTHROPIC_API_KEY": "NOT_CONFIGURED",
        "OPENROUTER_API_KEY": "NOT_CONFIGURED",
        "NEO4J_URI": "neo4j://127.0.0.1:7687",
        "NEO4J_PASSWORD": "PACKAGE_SAFE_TEST_ONLY_NEO4J_PASSWORD",
        "TELEGRAM_BOT_TOKEN": "NOT_CONFIGURED",
        "TELEGRAM_WEBHOOK_SECRET": "NOT_CONFIGURED",
        "EDGE_ENTRYPOINT": "main_sim_only",
        "EDGE_RUNTIME_MODE": "sim_only",
        "RUN_GCODE_TARGET": "simulation",
        "RUN_PERMISSION_GATE": "0",
        "ALLOW_SIMULATION_RUN": "1",
        "MACHINE_COMMAND_GATE": "0",
        "NX_PORT": "6001",
        "NXMCD_ENDIAN": ">",
        "NX_FEEDBACK_FRAME_BYTES": "100",
        "NX_ENDIAN_CONFIRMED": "0",
        "NX_FRAMING_CONFIRMED": "0",
        "NX_COLLISION_MAPPING_VERIFIED": "0",
        "NX_TERMINAL_THRESHOLDS_CALIBRATED": "0",
        "MACHINE_CONFIG_HASH": "UNSET_REQUIRED_FOR_PRODUCTION",
        "MATLAB_MODEL_HASH": "UNSET_REQUIRED_FOR_PRODUCTION",
        "NX_MODEL_HASH": "UNSET_REQUIRED_FOR_PRODUCTION",
    }
    lines: list[str] = []
    seen: set[str] = set()
    for raw in example.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#") or "=" not in raw:
            lines.append(raw)
            continue
        key, value = raw.split("=", 1)
        name = key.strip()
        seen.add(name)
        if name in safe:
            value = safe[name]
        elif value.strip().startswith("<") and value.strip().endswith(">"):
            value = "NOT_CONFIGURED"
        lines.append(f"{key}={value}")
    for name, value in safe.items():
        if name not in seen:
            lines.append(f"{name}={value}")
    return "\n".join(lines) + "\n"


@contextmanager
def temporary_safe_env():
    env_path = ROOT / ".env"
    backup = ROOT / ".env.mission11_v2_backup"
    safe_bytes = _safe_env_text().encode("utf-8")
    if backup.exists():
        if not env_path.exists() or env_path.read_bytes() == safe_bytes:
            env_path.unlink(missing_ok=True)
            backup.replace(env_path)
        else:
            raise RuntimeError("Conflicting .env and .env.mission11_v2_backup; resolve manually")
    existed = env_path.exists()
    already_safe = existed and env_path.read_bytes() == safe_bytes
    backup_used = False
    if not already_safe:
        if existed:
            env_path.replace(backup)
            backup_used = True
        env_path.write_bytes(safe_bytes)
    policy = {
        "temporary_safe_env": not already_safe,
        "original_env_present": existed,
        "existing_env_was_package_safe": already_safe,
        "atomic_backup_used": backup_used,
        "real_credentials_used": False,
    }
    try:
        yield policy
    finally:
        if already_safe:
            return
        env_path.unlink(missing_ok=True)
        if backup_used and backup.exists():
            backup.replace(env_path)


def run_check(name: str, argv: list[str], out_dir: Path, level: str = "L2") -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    # Third-party pytest plugins from the host Python environment must not alter
    # or hang package verification. The project integration suite is self-contained.
    if "pytest" in argv:
        env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    proc = subprocess.run(argv, cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240)
    stdout_file = f"{name}.stdout.txt"
    stderr_file = f"{name}.stderr.txt"
    (out_dir / stdout_file).write_text(proc.stdout, encoding="utf-8")
    (out_dir / stderr_file).write_text(proc.stderr, encoding="utf-8")
    return {
        "name": name,
        "command": argv,
        "working_directory": str(ROOT),
        "exit_code": proc.returncode,
        "result": "PASS" if proc.returncode == 0 else "FAIL",
        "verification_level": level,
        "stdout_file": stdout_file,
        "stderr_file": stderr_file,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    py = sys.executable
    checks = [
        ("compileall", [py, "-m", "compileall", "-q", "cloud_backend", "edge_backend", "mcp_server", "tools", "eval", "integration_tests"], "L1"),
        ("pytest_isolated", [py, "tools/run_pytest_isolated.py", "--tests-dir", "integration_tests", "--report", str(out_dir / "PYTEST_ISOLATED_REPORT.json")], "L2"),
        ("frontend_js", [py, "tools/check_frontend_js.py"], "L2"),
        ("mcp_smoke", [py, "eval/mcp_smoke_test.py"], "L2"),
        ("mission09_eval", [py, "eval/mission09_check_gate_arc_knowledge_eval.py"], "L2"),
        ("connection_audit", [py, "tools/full_connection_audit.py", "--mode", "static", "--profile", "all", "--out-dir", str(out_dir / "connection_audit"), "--strict"], "L2"),
    ]
    records: list[dict[str, Any]] = []
    with temporary_safe_env() as env_policy:
        for name, argv, level in checks:
            print(f"[Mission11V2] {name} ...", flush=True)
            try:
                record = run_check(name, argv, out_dir, level)
            except subprocess.TimeoutExpired as exc:
                record = {"name": name, "command": argv, "working_directory": str(ROOT), "exit_code": None, "result": "TIMEOUT", "verification_level": level, "error": str(exc)}
            records.append(record)
            print(f"[Mission11V2] {name}: {record['result']}", flush=True)
    overall = "PASS" if all(item["result"] == "PASS" for item in records) else "FAIL"
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall": overall,
        "scope": "static_and_sandbox_only",
        "environment_policy": env_policy,
        "machine_commands_issued": 0,
        "real_matlab_verified": False,
        "real_nx_verified": False,
        "real_fluidnc_verified": False,
        "physical_machine_verified": False,
        "checks": records,
    }
    (out_dir / "MISSION11_V2_STATIC_VERIFY_SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"overall": overall, "out_dir": str(out_dir)}, ensure_ascii=False))
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
