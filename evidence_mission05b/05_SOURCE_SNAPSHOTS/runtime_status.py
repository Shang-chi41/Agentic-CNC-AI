"""Unified runtime status heartbeat for Mission 05B.

This module is the single Edge-side contract for runtime / connection /
dataflow / gate state.  It deliberately separates:
- CONNECTION: service/socket/ping liveness;
- RUNTIME: which entrypoint is alive (main.py or main_sim_only.py);
- DATAFLOW: who owns NX MCD data at the moment;
- GATE: whether real machine execution is guarded.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Callable, Any

from edge_backend.utils.logger import get_logger
from edge_backend.utils.time_helper import now_iso

logger = get_logger(__name__)

RuntimeSnapshotFactory = Callable[[], dict[str, Any]]


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def runtime_env_contract(entrypoint: str) -> dict[str, Any]:
    """Return non-secret runtime env needed by Cloud/HMI."""
    inferred_mode = "sim_only" if entrypoint == "main_sim_only" else "machine"
    return {
        "edge_runtime_mode": os.getenv("EDGE_RUNTIME_MODE", inferred_mode),
        "run_gcode_target": os.getenv("RUN_GCODE_TARGET", "simulation"),
        "run_permission_gate": _env_bool("RUN_PERMISSION_GATE", False),
        "allow_simulation_run": _env_bool("ALLOW_SIMULATION_RUN", False),
        "matlab_ip": os.getenv("MATLAB_IP", "127.0.0.1"),
        "matlab_send_port": int(os.getenv("MATLAB_SEND_PORT", "5000")),
        "matlab_recv_port": int(os.getenv("MATLAB_RECV_PORT", "5001")),
        "nx_host": os.getenv("NX_HOST", "0.0.0.0"),
        "nx_port": int(os.getenv("NX_PORT", "6001")),
        "fluidnc_host": os.getenv("FLUIDNC_HOST", ""),
        "fluidnc_port": int(os.getenv("FLUIDNC_PORT", "23")),
    }


class RuntimeStatusHeartbeat:
    """Periodic Edge -> Cloud runtime heartbeat."""

    def __init__(
        self,
        *,
        entrypoint: str,
        sync_worker,
        snapshot_factory: RuntimeSnapshotFactory,
        interval_s: float | None = None,
    ) -> None:
        self.entrypoint = entrypoint
        self.sync_worker = sync_worker
        self.snapshot_factory = snapshot_factory
        self.interval_s = max(1.0, float(interval_s if interval_s is not None else os.getenv("RUNTIME_HEARTBEAT_S", "3.0")))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name=f"RuntimeHeartbeat-{self.entrypoint}", daemon=True)
        self._thread.start()
        logger.info("✅ Runtime heartbeat started entrypoint=%s interval=%.1fs", self.entrypoint, self.interval_s)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        logger.info("Runtime heartbeat stopped entrypoint=%s", self.entrypoint)

    def build_record(self) -> dict[str, Any]:
        base = {
            "runtime_id": f"edge:{self.entrypoint}",
            "entrypoint": self.entrypoint,
            "timestamp": now_iso(),
            "env": runtime_env_contract(self.entrypoint),
        }
        try:
            snap = self.snapshot_factory() or {}
        except Exception as exc:
            logger.warning("Runtime snapshot failed entrypoint=%s: %s", self.entrypoint, exc)
            snap = {"snapshot_error": str(exc)}
        base.update(snap)
        base.setdefault("runtime", {})
        base["runtime"].setdefault("entrypoint", self.entrypoint)
        base["runtime"].setdefault("alive", True)
        base["runtime"].setdefault("mode", base["env"].get("edge_runtime_mode"))
        return base

    def _loop(self) -> None:
        while not self._stop.is_set():
            record = self.build_record()
            try:
                if self.sync_worker is not None:
                    self.sync_worker.push_runtime_status(record)
            except Exception as exc:
                logger.debug("runtime status push skipped: %s", exc)
            self._stop.wait(self.interval_s)
