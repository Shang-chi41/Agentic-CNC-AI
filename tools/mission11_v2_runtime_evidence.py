#!/usr/bin/env python3
"""Passive Mission 11 V2 runtime evidence collector.

Only HTTP GET is permitted.  This tool cannot HOME, JOG, CHECK, CONFIRM, RUN,
RESET, HOLD, E-STOP or otherwise issue a machine side effect.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_json(url: str, *, token: str = "", timeout: float = 5.0) -> dict[str, Any]:
    headers = {"Accept": "application/json", "User-Agent": "mission11-v2-passive-evidence/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def check_status(status: dict[str, Any], profile: str) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    runtime = status.get("runtime") or {}
    connection = status.get("connection") or {}
    gate = status.get("gate") or {}
    workflow = status.get("workflow_state") or {}
    if profile == "observe":
        return True, reasons
    if runtime.get("active_entrypoint") != "main":
        reasons.append(f"active_entrypoint={runtime.get('active_entrypoint')!r}, expected 'main'")
    for key in ("fluidnc", "matlab_main", "nxmcd"):
        if not bool((connection.get(key) or {}).get("connected")):
            reasons.append(f"{key} is not connected")
    if not workflow:
        reasons.append("canonical workflow_state is missing")
    if profile == "production-ready" and not bool(gate.get("machine_run_allowed")):
        for item in gate.get("reasons") or [gate.get("reason") or "unknown gate reason"]:
            reasons.append(f"run gate: {item}")
    return not reasons, reasons


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--profile", choices=("observe", "connections", "production-ready"), default="connections")
    parser.add_argument("--out-dir", default="agentic_execution_kit/MISSION_11_V2_STATIC_RUNTIME/EVIDENCE/RUNTIME/latest")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    token = os.getenv("CNC_JWT_TOKEN", "").strip()
    snapshots: list[dict[str, Any]] = []
    errors: list[str] = []
    started = time.monotonic()
    health = None
    try:
        health = get_json(args.base_url.rstrip("/") + "/health", timeout=args.timeout)
    except Exception as exc:
        errors.append(f"health request failed: {type(exc).__name__}: {exc}")

    while True:
        try:
            status = get_json(args.base_url.rstrip("/") + "/api/system/status", token=token, timeout=args.timeout)
            snapshots.append({"collected_at": now_iso(), "status": status})
        except urllib.error.HTTPError as exc:
            errors.append(f"system status HTTP {exc.code}; set CNC_JWT_TOKEN for authenticated routes")
        except Exception as exc:
            errors.append(f"system status failed: {type(exc).__name__}: {exc}")
        if time.monotonic() - started >= max(0.0, args.duration):
            break
        time.sleep(max(0.1, args.interval))

    snapshot_file = out_dir / "system_status.jsonl"
    with snapshot_file.open("w", encoding="utf-8") as handle:
        for item in snapshots:
            handle.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")
    final = snapshots[-1]["status"] if snapshots else {}
    contract_ok, reasons = check_status(final, args.profile)
    summary = {
        "tool": "mission11_v2_runtime_evidence",
        "passive_only": True,
        "machine_commands_issued": 0,
        "generated_at": now_iso(),
        "base_url": args.base_url,
        "profile": args.profile,
        "duration_s": args.duration,
        "snapshot_count": len(snapshots),
        "health": health,
        "errors": list(dict.fromkeys(errors)),
        "contract_ok": bool(snapshots) and not errors and contract_ok,
        "contract_reasons": reasons,
        "evidence_level": "L3" if snapshots else "L0",
        "required_next_level": "L4 real MATLAB/NX/FluidNC; L5 physical CNC",
        "snapshot_file": str(snapshot_file),
    }
    (out_dir / "runtime_evidence_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["contract_ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
