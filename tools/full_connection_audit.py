#!/usr/bin/env python3
"""Full-system connection audit for the CNC Digital Twin project.

Modes:
  static     - no network, verifies configuration/code contracts and MCP stdio.
  safe-live  - static + passive local port inspection + Cloud/Mongo/Neo4j safe probes.
  full-live  - safe-live + explicit active FluidNC/MQTT/Telegram/LLM probes.

The audit never sends G-code and never connects to NX MCD as a fake client.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import re
import socket
import subprocess
import sys
import time
from typing import Any
from urllib.parse import urlparse

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None


SENSITIVE_MARKERS = ("KEY", "TOKEN", "PASSWORD", "SECRET", "AUTH")
EXPECTED_TOOLS = {
    "get_machine_status",
    "get_latest_alarms",
    "get_sensor_history",
    "get_simulation_data",
    "validate_gcode",
    "check_gcode_simulation",
    "get_gcode_result",
    "get_neo4j_context",
}

WORKFLOW_DIMENSIONS = {
    "connection",
    "availability",
    "activity",
    "completion",
    "approval",
    "run_permission",
}


def _ensure_project_root_on_path(root: Path) -> None:
    """Make project packages importable for every supported CLI invocation.

    ``python tools/full_connection_audit.py`` starts with ``tools/`` on
    ``sys.path`` while ``python -m tools.full_connection_audit`` starts with
    the project root.  Runtime checks import ``edge_backend`` and must behave
    identically in both cases.
    """

    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


def _matlab_bridge_listener_contract(
    listeners: set[int], ports: dict[str, int]
) -> tuple[str, str, str, dict[str, Any]]:
    """Classify the three MATLAB Bridge listeners as one runtime dependency.

    Ports 5000/5100/5101 are opened by the same MATLAB Bridge process.  Three
    absent ports therefore mean "bridge not running", not three independent
    component failures.  A partial group is the actual suspicious condition.
    """

    present = {name: port in listeners for name, port in ports.items()}
    count = sum(present.values())
    evidence = {"ports": ports, "present": present, "passive_only": True}
    if count == len(ports):
        return (
            "PASS",
            "NOTE",
            "MATLAB Bridge listener group is active on all three ports",
            evidence,
        )
    if count == 0:
        return (
            "INACTIVE",
            "NOTE",
            "MATLAB Bridge process is not detected; ports 5000/5100/5101 are one inactive group",
            evidence,
        )
    return (
        "WARN",
        "MAJOR",
        "MATLAB Bridge listener group is only partially active",
        evidence,
    )


def _validate_unified_status_contract(data: Any) -> tuple[bool, list[str], list[str]]:
    """Validate the canonical status shape without inferring runtime truth."""

    if not isinstance(data, dict):
        return False, ["<response_not_object>"], sorted(WORKFLOW_DIMENSIONS)
    required_top = {"runtime", "connection", "dataflow", "workflow_state", "gate"}
    missing_top = sorted(key for key in required_top if not isinstance(data.get(key), dict))
    workflow = data.get("workflow_state") if isinstance(data.get("workflow_state"), dict) else {}
    missing_dimensions = sorted(key for key in WORKFLOW_DIMENSIONS if key not in workflow)
    return not missing_top and not missing_dimensions, missing_top, missing_dimensions


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


@dataclass
class Check:
    check_id: str
    layer: str
    component: str
    verification_level: str
    status: str
    severity: str
    required: bool
    summary: str
    evidence: dict[str, Any]


class Audit:
    def __init__(self, root: Path, mode: str, profile: str) -> None:
        self.root = root
        self.mode = mode
        self.profile = profile
        self.checks: list[Check] = []
        self.env = self._read_env(root / ".env")
        self.example_env = self._read_env(root / ".env.example")

    @staticmethod
    def _read_env(path: Path) -> dict[str, str]:
        data: dict[str, str] = {}
        if not path.exists():
            return data
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            data[k.strip()] = v.strip()
        return data

    def add(
        self,
        check_id: str,
        layer: str,
        component: str,
        level: str,
        status: str,
        severity: str,
        summary: str,
        evidence: dict[str, Any] | None = None,
        required: bool = True,
    ) -> None:
        self.checks.append(Check(
            check_id=check_id,
            layer=layer,
            component=component,
            verification_level=level,
            status=status,
            severity=severity,
            required=required,
            summary=summary,
            evidence=evidence or {},
        ))

    @staticmethod
    def _safe_value(key: str, value: str) -> str:
        if any(marker in key.upper() for marker in SENSITIVE_MARKERS):
            return "<redacted>"
        if "://" in value:
            parsed = urlparse(value)
            if parsed.password:
                host = parsed.hostname or ""
                port = f":{parsed.port}" if parsed.port else ""
                return f"{parsed.scheme}://<redacted>@{host}{port}{parsed.path}"
        return value

    def _file_contains(self, rel: str, *needles: str) -> tuple[bool, list[str]]:
        p = self.root / rel
        if not p.exists():
            return False, [f"missing:{rel}"]
        text = p.read_text(encoding="utf-8", errors="replace")
        missing = [n for n in needles if n not in text]
        return not missing, missing

    def static_checks(self) -> None:
        required_paths = [
            "cloud_backend/main.py",
            "cloud_backend/routes/system_routes.py",
            "cloud_backend/routes/sync_routes.py",
            "edge_backend/main.py",
            "edge_backend/main_sim_only.py",
            "edge_backend/runtime_status.py",
            "edge_backend/workers/sync_worker.py",
            "edge_backend/communication/telnet_client.py",
            "edge_backend/simulation/matlab_sender.py",
            "edge_backend/simulation/matlab_receiver.py",
            "edge_backend/simulation/nxmcd_client.py",
            "edge_backend/ai/mcp_client_adapter.py",
            "mcp_server/cnc_tools_server.py",
            "frontend/js/monitor.js",
            "frontend/js/control.js",
            "matlab_bridge/run_edge_matlab_bridge_R2023b_CNC3_quiet_FIXED.m",
            "scripts/RUN_70_MAIN_MACHINE.ps1",
            "scripts/RUN_71_MAIN_SIM_ONLY.ps1",
        ]
        missing = [p for p in required_paths if not (self.root / p).exists()]
        self.add(
            "S001", "static", "project_inventory", "static",
            "PASS" if not missing else "FAIL",
            "BLOCKER" if missing else "NOTE",
            "Required architecture files present" if not missing else "Missing architecture files",
            {"missing": missing},
        )

        env_keys = set(self.env)
        example_keys = set(self.example_env)
        self.add(
            "S002", "config", "env_contract", "static",
            "PASS" if env_keys == example_keys else "FAIL",
            "MAJOR" if env_keys != example_keys else "NOTE",
            "`.env` and `.env.example` key parity",
            {
                "env_key_count": len(env_keys),
                "example_key_count": len(example_keys),
                "only_env": sorted(env_keys - example_keys),
                "only_example": sorted(example_keys - env_keys),
            },
        )

        required_env = {
            "CLOUD_URL", "MONGO_URI", "SYNC_API_KEY",
            "MATLAB_IP", "MATLAB_SEND_PORT", "MATLAB_RECV_PORT",
            "SIMULINK_GCODE_PORT", "SIMULINK_FRAME_PORT",
            "NX_HOST", "NX_PORT", "FLUIDNC_HOST", "FLUIDNC_PORT",
            "MQTT_BROKER", "MQTT_PORT", "NEO4J_URI",
            "NEO4J_USER", "NEO4J_PASSWORD",
            "AI_PROVIDER", "AI_TOOL_TRANSPORT", "MCP_TOOL_SERVER_MODULE",
        }
        absent = sorted(k for k in required_env if not self.env.get(k, "").strip())
        self.add(
            "S003", "config", "required_env", "static",
            "PASS" if not absent else "FAIL",
            "CRITICAL" if absent else "NOTE",
            "Required connection configuration is present",
            {"missing_or_empty": absent},
        )

        # Machine/sim launch profile is the effective safety source.
        machine_ok, machine_missing = self._file_contains(
            "scripts/RUN_70_MAIN_MACHINE.ps1",
            '$env:EDGE_RUNTIME_MODE="machine"',
            '$env:RUN_GCODE_TARGET="machine"',
            '$env:RUN_PERMISSION_GATE="1"',
            '$env:ALLOW_SIMULATION_RUN="0"',
        )
        sim_ok, sim_missing = self._file_contains(
            "scripts/RUN_71_MAIN_SIM_ONLY.ps1",
            '$env:EDGE_RUNTIME_MODE="sim_only"',
            '$env:RUN_GCODE_TARGET="simulation"',
            '$env:RUN_PERMISSION_GATE="0"',
            '$env:ALLOW_SIMULATION_RUN="1"',
        )
        self.add(
            "S004", "safety", "runtime_profiles", "static",
            "PASS" if machine_ok and sim_ok else "FAIL",
            "CRITICAL" if not (machine_ok and sim_ok) else "NOTE",
            "Machine and simulation launch profiles remain separated",
            {"machine_missing": machine_missing, "sim_missing": sim_missing},
        )

        direct_hazard = (
            self.env.get("RUN_GCODE_TARGET", "").lower() == "machine"
            and self.env.get("RUN_PERMISSION_GATE", "0").lower() not in {"1", "true", "yes", "on"}
        )
        self.add(
            "S005", "safety", "direct_env_profile", "static",
            "WARN" if direct_hazard else "PASS",
            "CRITICAL" if direct_hazard else "NOTE",
            (
                "Direct `python -m edge_backend.main` would inherit machine target with gate disabled; "
                "use RUN_70_MAIN_MACHINE.bat"
                if direct_hazard else
                "Direct environment does not combine machine target with disabled gate"
            ),
            {
                "run_gcode_target": self.env.get("RUN_GCODE_TARGET"),
                "run_permission_gate": self.env.get("RUN_PERMISSION_GATE"),
                "effective_machine_launcher": "scripts/RUN_70_MAIN_MACHINE.ps1",
            },
            required=False,
        )

        frontend_ok = True
        frontend_evidence: dict[str, Any] = {}
        for rel in ("frontend/js/monitor.js", "frontend/js/control.js"):
            text = (self.root / rel).read_text(encoding="utf-8", errors="replace")
            frontend_evidence[rel] = {
                "uses_unified_status": "/api/system/status" in text,
                "uses_legacy_monitor_connection": "/api/monitor/connection" in text,
            }
            frontend_ok &= "/api/system/status" in text and "/api/monitor/connection" not in text
        self.add(
            "S006", "frontend", "unified_status_consumer", "static",
            "PASS" if frontend_ok else "FAIL",
            "MAJOR" if not frontend_ok else "NOTE",
            "Frontend renders the unified system status contract",
            frontend_evidence,
        )

        status_ok, status_missing = self._file_contains(
            "cloud_backend/routes/system_routes.py",
            '"fluidnc"', '"matlab_main"', '"sim_test"', '"nxmcd"', '"mongodb"',
            '"runtime"', '"connection"', '"dataflow"', '"gate"',
            "main.fluidnc_telnet_socket",
            "main_sim_only.runtime_heartbeat",
            "nxmcd_tcp_client_socket",
            "cloud_mongo_ping",
        )
        self.add(
            "S007", "cloud", "system_status_source_contract", "static",
            "PASS" if status_ok else "FAIL",
            "CRITICAL" if not status_ok else "NOTE",
            "Cloud status separates connection/runtime/dataflow/gate",
            {"missing_contract_tokens": status_missing},
        )

        main_ok, main_missing = self._file_contains(
            "edge_backend/main.py",
            "fluidnc.connection_status()",
            "matlab_sender.status()",
            "matlab_receiver.status()",
            "nxmcd_client.status()",
            '"sim_test": {"connected": False',
            "RuntimeStatusHeartbeat",
        )
        sim_ok2, sim_missing2 = self._file_contains(
            "edge_backend/main_sim_only.py",
            '"fluidnc": {"connected": False',
            '"sim_test": {',
            '"connected": True',
            "main_sim_only never opens the machine run gate",
            "RuntimeStatusHeartbeat",
        )
        self.add(
            "S008", "edge", "runtime_snapshot_contract", "static",
            "PASS" if main_ok and sim_ok2 else "FAIL",
            "CRITICAL" if not (main_ok and sim_ok2) else "NOTE",
            "main and main_sim_only report separate connection truth",
            {"main_missing": main_missing, "sim_missing": sim_missing2},
        )

        ports = {}
        for key in (
            "MATLAB_SEND_PORT", "MATLAB_RECV_PORT",
            "SIMULINK_GCODE_PORT", "SIMULINK_FRAME_PORT",
            "NX_PORT", "FLUIDNC_PORT", "MQTT_PORT",
        ):
            try:
                ports[key] = int(self.env.get(key, ""))
            except Exception:
                ports[key] = None
        local_listener_keys = [
            "MATLAB_SEND_PORT", "MATLAB_RECV_PORT",
            "SIMULINK_GCODE_PORT", "SIMULINK_FRAME_PORT", "NX_PORT",
        ]
        local_values = [ports[k] for k in local_listener_keys if ports[k] is not None]
        distinct = len(local_values) == len(set(local_values))
        expected = {
            "MATLAB_SEND_PORT": 5000,
            "MATLAB_RECV_PORT": 5001,
            "SIMULINK_GCODE_PORT": 5100,
            "SIMULINK_FRAME_PORT": 5101,
            "NX_PORT": 6001,
        }
        aligned = all(ports.get(k) == v for k, v in expected.items())
        self.add(
            "S009", "config", "port_contract", "static",
            "PASS" if distinct and aligned else "FAIL",
            "CRITICAL" if not distinct else ("MAJOR" if not aligned else "NOTE"),
            "Core TCP ports are distinct and match the MATLAB/NX contract",
            {"ports": ports, "expected": expected, "distinct": distinct},
        )

        bridge_ok, bridge_missing = self._file_contains(
            "matlab_bridge/run_edge_matlab_bridge_R2023b_CNC3_quiet_FIXED.m",
            "MATLAB_SEND_PORT", "MATLAB_RECV_PORT",
            "SIMULINK_GCODE_PORT", "SIMULINK_FRAME_PORT",
        )
        self.add(
            "S010", "matlab", "bridge_env_contract", "static",
            "PASS" if bridge_ok else "FAIL",
            "MAJOR" if not bridge_ok else "NOTE",
            "MATLAB bridge reads the same four port variables",
            {"missing": bridge_missing},
        )

        # MCP smoke is safe and does not expose a network port.
        cmd = [sys.executable, "eval/mcp_smoke_test.py"]
        try:
            proc = subprocess.run(
                cmd, cwd=self.root, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=30,
            )
            tools = set()
            match = re.search(r"Tools:\s*(.+)", proc.stdout)
            if match:
                tools = {x.strip() for x in match.group(1).split(",") if x.strip()}
            ok = proc.returncode == 0 and tools == EXPECTED_TOOLS
            self.add(
                "S011", "mcp", "stdio_tool_server", "sandbox",
                "PASS" if ok else "FAIL",
                "BLOCKER" if not ok else "NOTE",
                "MCP stdio tools/list returns exactly 8 tools",
                {
                    "exit_code": proc.returncode,
                    "tools": sorted(tools),
                    "stdout_tail": proc.stdout[-1000:],
                    "stderr_tail": proc.stderr[-500:],
                },
            )
        except Exception as exc:
            self.add(
                "S011", "mcp", "stdio_tool_server", "sandbox",
                "FAIL", "BLOCKER", "MCP smoke execution failed",
                {"error": str(exc)},
            )

        selected_provider = self.env.get("AI_PROVIDER", "").strip().lower()
        provider_key_map = {
            "openrouter": "OPENROUTER_API_KEY",
            "gemini": "GEMINI_API_KEY",
            "claude": "ANTHROPIC_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "fcc": "FCC_AUTH_TOKEN",
            "ollama": "OLLAMA_BASE_URL",
            "rule_based": None,
            "emergency": None,
        }
        needed = provider_key_map.get(selected_provider)
        provider_config_ok = selected_provider in provider_key_map and (
            needed is None or bool(self.env.get(needed, "").strip())
        )
        self.add(
            "S012", "ai", "provider_configuration", "static",
            "PASS" if provider_config_ok else "FAIL",
            "CRITICAL" if not provider_config_ok else "NOTE",
            "Configured AI provider has its required connection setting",
            {
                "provider": selected_provider,
                "required_setting": needed,
                "setting_present": None if needed is None else bool(self.env.get(needed, "").strip()),
            },
        )

        sync_key_present = bool(self.env.get("SYNC_API_KEY", "").strip())
        sync_route_ok, sync_missing = self._file_contains(
            "cloud_backend/routes/sync_routes.py",
            "X-Sync-Key", "SYNC_API_KEY", "runtime_status",
        )
        sync_worker_ok, sync_worker_missing = self._file_contains(
            "edge_backend/workers/sync_worker.py",
            "X-Sync-Key", "push_runtime_status", "/api/sync/runtime_status",
        )
        self.add(
            "S013", "sync", "edge_cloud_sync", "static",
            "PASS" if sync_key_present and sync_route_ok and sync_worker_ok else "FAIL",
            "CRITICAL" if not (sync_key_present and sync_route_ok and sync_worker_ok) else "NOTE",
            "Edge→Cloud sync authentication and runtime heartbeat paths align",
            {
                "sync_key_present": sync_key_present,
                "route_missing": sync_missing,
                "worker_missing": sync_worker_missing,
            },
        )

        pose_ok, pose_missing = self._file_contains(
            "cloud_backend/routes/pose_routes.py",
            "/api/pose/publish", "/api/pose/latest", "/ws/pose", "decode_access_token",
        )
        monitor_ok, monitor_missing = self._file_contains(
            "frontend/js/monitor.js",
            "/ws/pose", "connectPoseStream",
        )
        self.add(
            "S014", "frontend_cloud", "pose_relay_contract", "static",
            "PASS" if pose_ok and monitor_ok else "FAIL",
            "MAJOR" if not (pose_ok and monitor_ok) else "NOTE",
            "Pose HTTP publish and authenticated WebSocket relay are wired",
            {"cloud_missing": pose_missing, "frontend_missing": monitor_missing},
        )

        docker_text = (self.root / "docker-compose.yml").read_text(encoding="utf-8", errors="replace")
        docker_ok = "8000:8000" in docker_text and "env_file:" in docker_text and "- .env" in docker_text
        uri_modes = {
            "mongo_local": self.env.get("MONGO_URI", "").startswith("mongodb://localhost"),
            "neo4j_local": "127.0.0.1" in self.env.get("NEO4J_URI", "") or "localhost" in self.env.get("NEO4J_URI", ""),
            "docker_comments_cloud_mongo": "MongoDB: Atlas" in docker_text,
            "docker_comments_cloud_neo4j": "AuraDB" in docker_text,
        }
        profile_drift = (
            (uri_modes["mongo_local"] and uri_modes["docker_comments_cloud_mongo"])
            or (uri_modes["neo4j_local"] and uri_modes["docker_comments_cloud_neo4j"])
        )
        self.add(
            "S015", "deployment", "docker_contract", "static",
            "WARN" if profile_drift else ("PASS" if docker_ok else "FAIL"),
            "MAJOR" if profile_drift else ("MAJOR" if not docker_ok else "NOTE"),
            (
                "Docker comments describe Atlas/Aura while current `.env` points to local services"
                if profile_drift else "Docker compose basic contract is aligned"
            ),
            {"docker_ok": docker_ok, **uri_modes},
            required=False,
        )

        # Lock the three user-confirmed runtime flows without pretending that
        # static strings prove timing or real device behavior.
        bridge_text = (self.root / "matlab_bridge/run_edge_matlab_bridge_R2023b_CNC3_quiet_FIXED.m").read_text(
            encoding="utf-8", errors="replace"
        )
        main_text = (self.root / "edge_backend/main.py").read_text(encoding="utf-8", errors="replace")
        validator_text = (self.root / "edge_backend/ai/gcode_validator.py").read_text(
            encoding="utf-8", errors="replace"
        )
        selector_text = (self.root / "edge_backend/simulation/control_selector.py").read_text(
            encoding="utf-8", errors="replace"
        )
        collector_text = (self.root / "edge_backend/collectors/telnet_collector.py").read_text(
            encoding="utf-8", errors="replace"
        )
        control_routes_text = (self.root / "cloud_backend/routes/control_routes.py").read_text(
            encoding="utf-8", errors="replace"
        )
        command_worker_text = (self.root / "edge_backend/workers/command_worker.py").read_text(
            encoding="utf-8", errors="replace"
        )
        telnet_text = (self.root / "edge_backend/communication/telnet_client.py").read_text(
            encoding="utf-8", errors="replace"
        )
        check_flow = all(token in bridge_text for token in (
            "CHECK RETURN TO START", "write_line_to_simulink", "check_id"
        )) and all(token in main_text for token in (
            "route_matlab_check(data)",
            "fluidnc.manual_motion_during_check",
            "clear_epoch=True",
        ))
        run_flow = all(token in validator_text for token in (
            "matlab_sender.send_run_preflight(",
            "matlab_sender.send_run_start(",
            "fluidnc.start_stream(",
            "threading.Barrier(3)",
            "parallel_fanout_skew_ms",
        )) and all(token in selector_text for token in (
            "stream_fluidnc", "nx_fanout_latency_ms"
        )) and all(token in collector_text for token in (
            "nx_control_selector.route_fluidnc_status",
            'event_bus.publish("run.nx_mirror_trace", trace)',
        )) and "matlab_sender.send_line" not in collector_text
        jog_flow = all(token in main_text for token in (
            "_nx_poll_from_fluidnc",
            "fluidnc.get_status()",
            "route_fluidnc_status(status, streaming=False)",
            "FluidNCManualMotionObserver",
        )) and all(token in control_routes_text for token in (
            '@router.post("/jog"', "status_code=423", "FluidNC WebUI"
        )) and "JOG command bị từ chối" in command_worker_text \
            and "$J=G91" not in telnet_text
        flow_ok = check_flow and run_flow and jog_flow
        self.add(
            "S016", "architecture", "three_primary_flow_ownership", "static",
            "PASS" if flow_ok else "FAIL",
            "CRITICAL" if not flow_ok else "NOTE",
            "CHECK, RUN and JOG ownership paths remain present",
            {
                "check_matlab_to_nx": check_flow,
                "run_parallel_exact_artifact_then_nx_from_fluidnc": run_flow,
                "jog_fluidnc_status_to_nx": jog_flow,
                "timing_proven": False,
                "runtime_proven": False,
            },
        )

    @staticmethod
    def _passive_listeners() -> set[int]:
        ports: set[int] = set()
        try:
            if platform.system().lower().startswith("win"):
                proc = subprocess.run(
                    ["netstat", "-ano", "-p", "tcp"],
                    capture_output=True, text=True, timeout=10,
                    encoding="utf-8", errors="replace",
                )
                for line in proc.stdout.splitlines():
                    if "LISTENING" not in line.upper():
                        continue
                    m = re.search(r":(\d+)\s+", line)
                    if m:
                        ports.add(int(m.group(1)))
            else:
                proc = subprocess.run(
                    ["sh", "-lc", "ss -ltnH 2>/dev/null || netstat -ltn 2>/dev/null"],
                    capture_output=True, text=True, timeout=10,
                    encoding="utf-8", errors="replace",
                )
                for line in proc.stdout.splitlines():
                    for m in re.finditer(r":(\d+)(?:\s|$)", line):
                        ports.add(int(m.group(1)))
        except Exception:
            pass
        return ports

    @staticmethod
    def _resolve_audit_jwt(
        requests_module: Any,
        cloud_url: str,
        explicit_jwt: str,
        username: str,
        password: str,
    ) -> tuple[str, str, str]:
        """Return ``token, source, error`` without exposing credentials."""

        token = explicit_jwt.strip()
        if token:
            return token, "provided_jwt", ""
        username = username.strip()
        if not username and not password:
            return "", "none", ""
        if not username or not password:
            return "", "login", "Both audit username and password are required"
        try:
            resp = requests_module.post(
                f"{cloud_url}/api/auth/login",
                json={"username": username, "password": password},
                timeout=5,
            )
            body = resp.json() if resp.content else {}
            token = str(body.get("access_token") or "")
            if resp.status_code == 200 and token:
                return token, "login", ""
            return "", "login", f"Login HTTP {resp.status_code}"
        except Exception as exc:
            return "", "login", str(exc)

    def safe_live_checks(
        self,
        jwt: str = "",
        username: str = "",
        password: str = "",
    ) -> None:
        import requests

        cloud_url = self.env.get("CLOUD_URL", "").rstrip("/")
        if cloud_url:
            try:
                resp = requests.get(f"{cloud_url}/health", timeout=4)
                ok = resp.status_code == 200 and resp.json().get("status") == "ok"
                self.add(
                    "L001", "cloud", "cloud_health", "safe-live",
                    "PASS" if ok else "FAIL",
                    "BLOCKER" if not ok else "NOTE",
                    "Cloud health endpoint reachable",
                    {"url": f"{cloud_url}/health", "http_status": resp.status_code},
                )
            except Exception as exc:
                self.add(
                    "L001", "cloud", "cloud_health", "safe-live",
                    "FAIL", "BLOCKER", "Cloud health endpoint unreachable",
                    {"url": f"{cloud_url}/health", "error": str(exc)},
                )
        else:
            self.add(
                "L001", "cloud", "cloud_health", "safe-live",
                "FAIL", "BLOCKER", "CLOUD_URL is missing", {},
            )

        # Mongo safe ping
        try:
            from edge_backend.database.mongo_client import ping as mongo_ping
            ok = bool(mongo_ping())
            self.add(
                "L002", "database", "mongodb", "safe-live",
                "PASS" if ok else "FAIL",
                "BLOCKER" if not ok else "NOTE",
                "MongoDB ping",
                {"uri": self._safe_value("MONGO_URI", self.env.get("MONGO_URI", ""))},
            )
        except Exception as exc:
            self.add(
                "L002", "database", "mongodb", "safe-live",
                "FAIL", "BLOCKER", "MongoDB ping raised an exception",
                {"error": str(exc)},
            )

        # Neo4j safe connectivity and RETURN 1.
        try:
            from neo4j import GraphDatabase
            uri = self.env.get("NEO4J_URI", "")
            user = self.env.get("NEO4J_USER", "")
            password = self.env.get("NEO4J_PASSWORD", "")
            database = self.env.get("NEO4J_DATABASE", "neo4j")
            with GraphDatabase.driver(uri, auth=(user, password), connection_timeout=4) as driver:
                driver.verify_connectivity()
                with driver.session(database=database) as session:
                    value = session.run("RETURN 1 AS ok").single()["ok"]
            ok = value == 1
            self.add(
                "L003", "database", "neo4j", "safe-live",
                "PASS" if ok else "FAIL",
                "BLOCKER" if not ok else "NOTE",
                "Neo4j connectivity and read query",
                {"uri": self._safe_value("NEO4J_URI", uri), "database": database},
            )
        except Exception as exc:
            self.add(
                "L003", "database", "neo4j", "safe-live",
                "FAIL", "BLOCKER", "Neo4j connectivity failed",
                {
                    "uri": self._safe_value("NEO4J_URI", self.env.get("NEO4J_URI", "")),
                    "error": str(exc),
                },
            )

        listeners = self._passive_listeners()
        independent_ports = {
            "cloud_8000": 8000,
            "edge_matlab_recv_5001": int(self.env.get("MATLAB_RECV_PORT", "5001")),
            "edge_nxmcd_6001": int(self.env.get("NX_PORT", "6001")),
        }
        for name, port in independent_ports.items():
            present = port in listeners
            self.add(
                f"P{port}", "passive_port", name, "safe-live",
                "PASS" if present else "UNKNOWN",
                "NOTE" if present else "MAJOR",
                f"TCP listener {'detected' if present else 'not detected'} on port {port}",
                {"port": port, "passive_only": True},
                required=False,
            )

        matlab_ports = {
            "edge_request_5000": int(self.env.get("MATLAB_SEND_PORT", "5000")),
            "simulink_gcode_5100": int(self.env.get("SIMULINK_GCODE_PORT", "5100")),
            "simulink_frame_5101": int(self.env.get("SIMULINK_FRAME_PORT", "5101")),
        }
        group_status, group_severity, group_summary, group_evidence = _matlab_bridge_listener_contract(
            listeners, matlab_ports
        )
        self.add(
            "L006", "runtime", "matlab_bridge_listener_group", "safe-live",
            group_status, group_severity, group_summary, group_evidence,
            required=False,
        )
        for name, port in matlab_ports.items():
            present = port in listeners
            self.add(
                f"P{port}", "passive_port", name, "safe-live",
                "PASS" if present else "INACTIVE",
                "NOTE",
                f"MATLAB Bridge group member {'detected' if present else 'not detected'} on port {port}",
                {"port": port, "passive_only": True, "group_check": "L006"},
                required=False,
            )

        # Authenticated unified status is the safest way to know actual device connectivity.
        resolved_jwt, auth_source, auth_error = self._resolve_audit_jwt(
            requests, cloud_url, jwt, username, password
        ) if cloud_url else ("", "none", "")
        if auth_error:
            self.add(
                "L004", "runtime", "unified_system_status", "safe-live",
                "FAIL", "BLOCKER", "Could not obtain JWT for unified system status",
                {"auth_source": auth_source, "error": auth_error},
            )
        elif resolved_jwt and cloud_url:
            try:
                resp = requests.get(
                    f"{cloud_url}/api/system/status",
                    headers={"Authorization": f"Bearer {resolved_jwt}"},
                    timeout=5,
                )
                data = resp.json() if resp.content else {}
                contract_ok, missing_top, missing_dimensions = _validate_unified_status_contract(data)
                ok = resp.status_code == 200 and contract_ok
                sanitized = {
                    "http_status": resp.status_code,
                    "auth_source": auth_source,
                    "runtime": data.get("runtime"),
                    "connection": data.get("connection"),
                    "dataflow": data.get("dataflow"),
                    "workflow_state": data.get("workflow_state"),
                    "gate": data.get("gate"),
                    "missing_top_level_contracts": missing_top,
                    "missing_workflow_dimensions": missing_dimensions,
                }
                self.add(
                    "L004", "runtime", "unified_system_status", "safe-live",
                    "PASS" if ok else "FAIL",
                    "BLOCKER" if not ok else "NOTE",
                    "Authenticated unified runtime/connection status",
                    sanitized,
                )
                if ok and data.get("runtime", {}).get("active_entrypoint") == "multiple":
                    self.add(
                        "L005", "runtime", "entrypoint_conflict", "safe-live",
                        "WARN", "CRITICAL",
                        "Both main and main_sim_only heartbeats are fresh",
                        {"live_entrypoints": data.get("runtime", {}).get("live_entrypoints")},
                        required=False,
                    )
            except Exception as exc:
                self.add(
                    "L004", "runtime", "unified_system_status", "safe-live",
                    "FAIL", "BLOCKER", "Could not read authenticated system status",
                    {"error": str(exc)},
                )
        else:
            self.add(
                "L004", "runtime", "unified_system_status", "safe-live",
                "SKIP", "NOTE",
                "No JWT or audit login credentials; canonical device connection truth was not read",
                {
                    "hint": (
                        "Pass --jwt, or set CONNECTION_AUDIT_USERNAME and "
                        "CONNECTION_AUDIT_PASSWORD for an authenticated login"
                    )
                },
                required=False,
            )

    @staticmethod
    def _tcp_probe(host: str, port: int, timeout: float = 3.0) -> tuple[bool, str]:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True, ""
        except Exception as exc:
            return False, str(exc)

    def full_live_checks(self, allow_ai_call: bool) -> None:
        # Active probes are explicit because they may create short sessions.
        host = self.env.get("FLUIDNC_HOST", "")
        port = int(self.env.get("FLUIDNC_PORT", "23"))
        ok, err = self._tcp_probe(host, port)
        self.add(
            "A001", "machine", "fluidnc_tcp", "full-live",
            "PASS" if ok else "FAIL",
            "CRITICAL" if not ok else "NOTE",
            "FluidNC TCP port reachable without sending a command",
            {"host": host, "port": port, "error": err},
        )

        mqtt_host = self.env.get("MQTT_BROKER", "")
        mqtt_port = int(self.env.get("MQTT_PORT", "1883"))
        ok, err = self._tcp_probe(mqtt_host, mqtt_port)
        self.add(
            "A002", "sensor", "mqtt_broker_tcp", "full-live",
            "PASS" if ok else "FAIL",
            "MAJOR" if not ok else "NOTE",
            "MQTT broker TCP port reachable",
            {"host": mqtt_host, "port": mqtt_port, "topic": self.env.get("MQTT_TOPIC"), "error": err},
        )

        token = self.env.get("TELEGRAM_BOT_TOKEN", "").strip()
        if token:
            try:
                import requests
                resp = requests.get(
                    f"https://api.telegram.org/bot{token}/getMe",
                    timeout=5,
                )
                body = resp.json() if resp.content else {}
                ok = resp.status_code == 200 and body.get("ok") is True
                self.add(
                    "A003", "notification", "telegram_bot", "full-live",
                    "PASS" if ok else "FAIL",
                    "MINOR" if not ok else "NOTE",
                    "Telegram bot authentication",
                    {"http_status": resp.status_code},
                    required=False,
                )
            except Exception as exc:
                self.add(
                    "A003", "notification", "telegram_bot", "full-live",
                    "FAIL", "MINOR", "Telegram getMe failed",
                    {"error": str(exc)}, required=False,
                )
        else:
            self.add(
                "A003", "notification", "telegram_bot", "full-live",
                "SKIP", "NOTE", "Telegram is not configured", {}, required=False,
            )

        if allow_ai_call:
            try:
                from edge_backend.ai.provider_manager import provider_manager
                answer = provider_manager.ask("Trả lời đúng một từ: OK")
                selected = self.env.get("AI_PROVIDER", "").strip().lower()
                active = str(provider_manager.active_provider or "").strip().lower()
                aliases = {"anthropic": "claude", "emergency": "rule_based"}
                expected = aliases.get(selected, selected)
                provider_ok = active == expected
                self.add(
                    "A004", "ai", "selected_llm_provider", "full-live",
                    "PASS" if provider_ok else "FAIL",
                    "CRITICAL" if not provider_ok else "NOTE",
                    (
                        "Configured LLM provider completed a minimal request"
                        if provider_ok else
                        "ProviderManager completed only through a fallback provider"
                    ),
                    {
                        "configured_provider": selected,
                        "active_provider": active,
                        "tier": provider_manager.tier,
                        "response_type": type(answer).__name__,
                    },
                )
            except Exception as exc:
                self.add(
                    "A004", "ai", "selected_llm_provider", "full-live",
                    "FAIL", "CRITICAL", "Configured LLM provider/fallback request failed",
                    {"error": str(exc)},
                )
        else:
            self.add(
                "A004", "ai", "selected_llm_provider", "full-live",
                "SKIP", "NOTE",
                "Billable/external AI call disabled; pass --allow-ai-call to test",
                {"provider": self.env.get("AI_PROVIDER")},
                required=False,
            )

    def summary(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for check in self.checks:
            counts[check.status] = counts.get(check.status, 0) + 1
        required_failures = [
            c for c in self.checks
            if c.required and c.status == "FAIL"
        ]
        critical_warnings = [
            c for c in self.checks
            if c.status in {"WARN", "FAIL"} and c.severity in {"BLOCKER", "CRITICAL"}
        ]
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": self.mode,
            "profile": self.profile,
            "counts": counts,
            "required_failure_count": len(required_failures),
            "critical_or_blocker_count": len(critical_warnings),
            "overall": "PASS" if not required_failures else "FAIL",
        }

    def write_reports(self, out_dir: Path) -> tuple[Path, Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        summary = self.summary()
        payload = {
            "summary": summary,
            "checks": [asdict(c) for c in self.checks],
            "security": {
                "secrets_included": False,
                "env_values_logged": False,
            },
        }
        json_path = out_dir / "CONNECTION_AUDIT_REPORT.json"
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        rows = []
        for c in self.checks:
            rows.append(
                f"| {c.check_id} | {c.component} | {c.verification_level} | "
                f"{c.status} | {c.severity} | {c.summary.replace('|', '/')} |"
            )
        md = f"""# Full System Connection Audit

Generated: {summary['generated_at']}

```text
Mode: {summary['mode']}
Profile: {summary['profile']}
Overall: {summary['overall']}
Required failures: {summary['required_failure_count']}
Critical/blocker findings: {summary['critical_or_blocker_count']}
```

## Results

| ID | Component | Level | Status | Severity | Summary |
|---|---|---|---|---|---|
{chr(10).join(rows)}

## Verification levels

```text
static     = source/config/contract only
sandbox    = local isolated process/test
safe-live  = safe runtime/database/passive-port checks
full-live  = explicitly allowed active network/provider probes
```

## Safety

- This audit never sends G-code.
- This audit never connects as a fake NX MCD client.
- LLM calls are disabled unless `--allow-ai-call` is supplied.
- Reports contain no API keys, passwords or tokens.

## Manual next step

Run while the intended runtime is active:

```bat
RUN_99_FULL_CONNECTION_AUDIT.bat safe-live all
```

To read the canonical unified status without storing a JWT in a file, set
temporary process credentials before the audit:

```powershell
$env:CONNECTION_AUDIT_USERNAME = "<operator>"
$env:CONNECTION_AUDIT_PASSWORD = "<password>"
RUN_99_FULL_CONNECTION_AUDIT.bat safe-live all
Remove-Item Env:CONNECTION_AUDIT_USERNAME, Env:CONNECTION_AUDIT_PASSWORD
```

For actual FluidNC/MQTT/LLM/Telegram probes:

```bat
RUN_99_FULL_CONNECTION_AUDIT.bat full-live all ai
```
"""
        md_path = out_dir / "CONNECTION_AUDIT_SUMMARY.md"
        md_path.write_text(md, encoding="utf-8")
        return json_path, md_path


def main() -> int:
    _configure_stdio()
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--mode", choices=["static", "safe-live", "full-live"], default="static")
    parser.add_argument("--profile", choices=["auto", "machine", "sim_only", "all"], default="all")
    parser.add_argument("--out-dir", default="reports/full_connection_audit")
    parser.add_argument("--jwt", default=os.getenv("CONNECTION_AUDIT_JWT", ""))
    parser.add_argument("--username", default=os.getenv("CONNECTION_AUDIT_USERNAME", ""))
    parser.add_argument("--password", default=os.getenv("CONNECTION_AUDIT_PASSWORD", ""))
    parser.add_argument("--allow-ai-call", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    _ensure_project_root_on_path(root)
    if load_dotenv is not None:
        load_dotenv(root / ".env", override=False)

    audit = Audit(root, args.mode, args.profile)
    audit.static_checks()
    if args.mode in {"safe-live", "full-live"}:
        audit.safe_live_checks(
            jwt=args.jwt,
            username=args.username,
            password=args.password,
        )
    if args.mode == "full-live":
        audit.full_live_checks(allow_ai_call=args.allow_ai_call)

    json_path, md_path = audit.write_reports(root / args.out_dir)
    summary = audit.summary()

    print("FULL CONNECTION AUDIT")
    print(f"Mode: {args.mode}")
    print(f"Overall: {summary['overall']}")
    print(f"Counts: {summary['counts']}")
    print(f"JSON: {json_path}")
    print(f"Summary: {md_path}")

    if args.strict and summary["required_failure_count"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
