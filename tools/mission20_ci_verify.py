#!/usr/bin/env python3
"""Reproducible Mission 20 verifier for a clean, secret-free package.

If the project has no ``.env``, this script creates a temporary local-only
sandbox configuration from ``.env.example``, runs all checks, then removes it.
An existing operator ``.env`` is never overwritten or deleted.
"""
from __future__ import annotations

import argparse
import compileall
import json
from pathlib import Path
import subprocess
import sys
from typing import Iterable


_SANDBOX_VALUES = {
    "MONGO_URI": "mongodb://127.0.0.1:27017/cnc_db_test",
    "JWT_SECRET": "sandbox-jwt-secret-2026-only-for-local-tests-long-enough",
    "BOOTSTRAP_ADMIN_USERNAME": "sandbox_admin",
    "BOOTSTRAP_ADMIN_PASSWORD": "Sandbox-Admin-Password-Only-For-Tests-2026!",
    "SYNC_API_KEY": "sandbox-sync-api-key-2026",
    "CLOUD_URL": "http://127.0.0.1:8000",
    "AI_PROVIDER": "openrouter",
    "FCC_AUTH_TOKEN": "sandbox-fcc-token",
    "GEMINI_API_KEY": "sandbox-gemini-key",
    "ANTHROPIC_API_KEY": "sandbox-anthropic-key",
    "OPENROUTER_API_KEY": "sandbox-openrouter-key",
    "MQTT_BROKER": "127.0.0.1",
    "MQTT_USERNAME": "sandbox-mqtt-user",
    "MQTT_PASSWORD": "sandbox-mqtt-password",
    "NEO4J_URI": "bolt://127.0.0.1:7687",
    "NEO4J_USER": "neo4j",
    "NEO4J_PASSWORD": "sandbox-neo4j-password",
    "TELEGRAM_BOT_TOKEN": "sandbox-telegram-token",
    "TELEGRAM_CHAT_ID": "123456789",
    "TELEGRAM_WEBHOOK_SECRET": "sandbox-webhook-secret-token-2026",
}


def _render_sandbox_env(example_text: str) -> str:
    replacements = {
        "<SET_IN_.env>": "sandbox-value",
        "<SET_FIRST_ADMIN_USERNAME>": _SANDBOX_VALUES["BOOTSTRAP_ADMIN_USERNAME"],
        "<SET_STRONG_FIRST_ADMIN_PASSWORD>": _SANDBOX_VALUES["BOOTSTRAP_ADMIN_PASSWORD"],
        "<SET_TRUSTED_MQTT_BROKER>": _SANDBOX_VALUES["MQTT_BROKER"],
        "<SET_RANDOM_WEBHOOK_SECRET>": _SANDBOX_VALUES["TELEGRAM_WEBHOOK_SECRET"],
    }
    text = example_text
    for old, new in replacements.items():
        text = text.replace(old, new)

    rendered: list[str] = []
    for line in text.splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key = line.split("=", 1)[0].strip()
            if key in _SANDBOX_VALUES:
                line = f"{key}={_SANDBOX_VALUES[key]}"
        rendered.append(line.rstrip())
    return "\n".join(rendered) + "\n"


def _run(cmd: list[str], *, cwd: Path) -> dict:
    print("+", " ".join(cmd), flush=True)
    proc = subprocess.run(
        cmd,
        cwd=cwd,
    )
    return {
        "command": " ".join(cmd),
        "exit_code": proc.returncode,
        "result": "PASS" if proc.returncode == 0 else "FAIL",
        "output": "streamed_to_parent_console",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--out", default="reports/mission20_ci_verification.json")
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    env_path = root / ".env"
    example_path = root / ".env.example"
    created_temp_env = False
    checks: list[dict] = []

    if not example_path.exists():
        raise SystemExit("Missing .env.example")

    try:
        if not env_path.exists():
            env_path.write_text(
                _render_sandbox_env(example_path.read_text(encoding="utf-8")),
                encoding="utf-8",
            )
            created_temp_env = True
            print("Created temporary sandbox .env for verification; no real secrets used")
        else:
            print("Using existing .env without modifying it")

        failures: list[str] = []

        if not compileall.compile_dir(root / "cloud_backend", quiet=1):
            failures.append("cloud_backend compileall")
        if not compileall.compile_dir(root / "edge_backend", quiet=1):
            failures.append("edge_backend compileall")

        from tools.mission19_ci_verify import scan_matlab_literal_newlines
        matlab_bad = scan_matlab_literal_newlines()
        if matlab_bad:
            failures.append("MATLAB literal newline: " + ", ".join(matlab_bad))

        for path in sorted((root / "frontend" / "js").glob("*.js")):
            item = _run(["node", "--check", str(path)], cwd=root)
            checks.append(item)
            if item["exit_code"] != 0:
                failures.append(f"node --check {path.relative_to(root)}")

        pytest_item = _run(
            [sys.executable, "-m", "pytest", "-q", "integration_tests"],
            cwd=root,
        )
        checks.append(pytest_item)
        if pytest_item["exit_code"] != 0:
            failures.append("pytest integration_tests")

        checks.insert(0, {
            "command": "compileall + MATLAB literal-newline scan",
            "exit_code": 0 if not failures or all(
                not item.startswith(("cloud_backend", "edge_backend", "MATLAB"))
                for item in failures
            ) else 1,
            "result": "PASS" if not any(
                item.startswith(("cloud_backend", "edge_backend", "MATLAB"))
                for item in failures
            ) else "FAIL",
            "output": "in_process",
        })


        result = "PASS" if not failures else "FAIL"
        payload = {
            "result": result,
            "evidence_level": "L2",
            "temporary_env_created": created_temp_env,
            "existing_env_preserved": not created_temp_env,
            "checks": checks,
            "failures": failures,
        }
        out = root / args.out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Mission20 CI verification: {result} -> {out}")
        return 0 if result == "PASS" else 1
    finally:
        if created_temp_env and env_path.exists():
            env_path.unlink()
            print("Removed temporary sandbox .env")


if __name__ == "__main__":
    raise SystemExit(main())
