#!/usr/bin/env python3
"""One-command L1/L2 verification for CNC Technical Assistant V2.

No live provider, Neo4j, MATLAB, NX MCD, FluidNC or physical machine command is
issued. External context/validator calls in generation evaluation are mocked.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import signal
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "agentic_execution_kit" / "MISSION_13_CNC_TECHNICAL_ASSISTANT_V2" / "EVIDENCE" / "latest"


def run(name: str, argv: list[str], out: Path, timeout: float = 180.0) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    stdout_path = out / f"{name}.stdout.txt"
    stderr_path = out / f"{name}.stderr.txt"
    with stdout_path.open("w", encoding="utf-8") as stdout_file, stderr_path.open("w", encoding="utf-8") as stderr_file:
        kwargs: dict[str, Any] = {
            "cwd": ROOT,
            "env": env,
            "stdout": stdout_file,
            "stderr": stderr_file,
            "text": True,
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        proc = subprocess.Popen(argv, **kwargs)
        try:
            code = proc.wait(timeout=timeout)
            result = "PASS" if code == 0 else "FAIL"
        except subprocess.TimeoutExpired:
            result, code = "TIMEOUT", None
            if os.name == "nt":
                proc.kill()
            else:
                os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
    return {
        "name": name,
        "command": argv,
        "result": result,
        "exit_code": code,
        "stdout_file": stdout_path.name,
        "stderr_file": stderr_path.name,
    }


def run_connection_audit(py: str, out: Path) -> dict[str, Any]:
    """Run audit and use its completed report as terminal evidence.

    Some legacy audit imports leave non-daemon threads alive after writing the
    final report. The verifier waits for the atomic report, validates PASS,
    then tears the process group down instead of hanging indefinitely.
    """
    audit_out = out / "connection_audit"
    audit_out.mkdir(parents=True, exist_ok=True)
    report = audit_out / "CONNECTION_AUDIT_REPORT.json"
    report.unlink(missing_ok=True)
    argv = [py, "tools/full_connection_audit.py", "--mode", "static", "--profile", "all", "--out-dir", str(audit_out), "--strict"]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    stdout_path = out / "connection_audit.stdout.txt"
    stderr_path = out / "connection_audit.stderr.txt"
    with stdout_path.open("w", encoding="utf-8") as stdout_file, stderr_path.open("w", encoding="utf-8") as stderr_file:
        kwargs: dict[str, Any] = {"cwd": ROOT, "env": env, "stdout": stdout_file, "stderr": stderr_file, "text": True}
        if os.name == "nt": kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else: kwargs["start_new_session"] = True
        proc = subprocess.Popen(argv, **kwargs)
        deadline = time.monotonic() + 120.0
        verdict = None
        while time.monotonic() < deadline:
            if report.exists():
                try:
                    data = json.loads(report.read_text(encoding="utf-8"))
                    verdict = str(data.get("overall") or (data.get("summary") or {}).get("overall") or "").upper()
                    if verdict in {"PASS", "FAIL"}:
                        break
                except Exception:
                    pass
            if proc.poll() is not None and not report.exists():
                break
            time.sleep(0.25)
        if proc.poll() is None:
            if os.name == "nt": proc.kill()
            else: os.killpg(proc.pid, signal.SIGKILL)
        try: proc.wait(timeout=5)
        except subprocess.TimeoutExpired: pass
    result = "PASS" if verdict == "PASS" else "FAIL"
    return {"name": "connection_audit", "command": argv, "result": result, "exit_code": 0 if result == "PASS" else 1, "report_file": str(report.relative_to(out)) if report.exists() else None}


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    out = args.out_dir.resolve(); out.mkdir(parents=True, exist_ok=True)
    py = sys.executable
    focused_files = [
        ROOT / "integration_tests/test_mission06g2_agentic_geometry_contract.py",
        ROOT / "integration_tests/test_mission06g3_context_priority_geometry.py",
        ROOT / "integration_tests/test_mission06g_agentic_flexible_gcode.py",
        ROOT / "integration_tests/test_mission08_agentic_flexibility_core.py",
        ROOT / "integration_tests/test_mission08_agentic_flexibility_eval_harness.py",
        ROOT / "integration_tests/test_mission11_v2_static_runtime_contracts.py",
        ROOT / "integration_tests/test_t12_control_auto_chat_boot.py",
        ROOT / "integration_tests/test_t13_cnc_technical_assistant_v2.py",
    ]
    checks = [
        ("compileall", [py, "-m", "compileall", "-q", "cloud_backend", "edge_backend", "mcp_server", "tools", "eval", "integration_tests"], 180),
        ("pytest_focused", [py, "tools/run_pytest_force_exit.py", "-q", *[str(p) for p in focused_files]], 180),
        ("frontend_js", [py, "tools/check_frontend_js.py"], 120),
        ("mcp_smoke", [py, "eval/mcp_smoke_test.py"], 120),
        ("mission09_eval", [py, "eval/mission09_check_gate_arc_knowledge_eval.py"], 120),
        ("agentic_flexibility_eval", [py, "eval/agentic_flexibility_eval.py"], 120),
        ("operator_language_eval", [py, "eval/operator_language_eval_v2.py"], 120),
        ("generation_eval", [py, "eval/cnc_assistant_generation_eval_v2.py"], 120),
    ]
    records = []
    for name, argv, timeout in checks:
        print(f"[Mission13] {name} ...", flush=True)
        record = run(name, argv, out, timeout)
        records.append(record)
        print(f"[Mission13] {name}: {record['result']}", flush=True)
    overall = "PASS" if all(r["result"] == "PASS" for r in records) else "FAIL"
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall": overall,
        "scope": "L1_L2_static_service_free_focused; full regression and connection audit are recorded in mission evidence",
        "machine_commands_issued": 0,
        "live_provider_verified": False,
        "live_neo4j_verified": False,
        "real_matlab_nx_fluidnc_verified": False,
        "physical_machine_verified": False,
        "checks": records,
    }
    (out / "MISSION13_VERIFY_SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"overall": overall, "out_dir": str(out)}, ensure_ascii=False))
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
