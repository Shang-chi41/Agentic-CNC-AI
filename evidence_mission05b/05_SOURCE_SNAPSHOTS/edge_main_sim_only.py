"""
edge_backend/main_sim_only.py

Simulation-only Edge entrypoint for the HMI -> Edge -> MATLAB/Simulink -> Edge -> NX MCD loop.

Starts only the services needed for offline CHECK/simulation:
  1. MongoDB
  2. MatlabReceiver on MATLAB_RECV_PORT=5001
  3. MatlabSender to MATLAB_SEND_PORT=5000
  4. GcodeSimDispatchWorker: GCode_Files -> MatlabSender
  5. NXMCDClient server on NX_PORT=6001
  6. NX Control Selector routing simulation.data -> NX MCD
  7. SyncWorker relay to Cloud/HMI when CLOUD_URL is configured
  8. AIWorker so HMI/Chat jobs with action=check_gcode can trigger MATLAB CHECK

It deliberately DOES NOT start FluidNC/TelnetCollector/CommandWorker/SensorWorker.
Use this when the real machine is not connected and you only want simulation/NX MCD.
"""

# ruff: noqa: E402
from __future__ import annotations

import os
import signal
import time

from dotenv import load_dotenv

load_dotenv()

from edge_backend.database.mongo_client import get_db, ping as mongo_ping
from edge_backend.internal.event_bus import event_bus
from edge_backend.runtime_status import RuntimeStatusHeartbeat
from edge_backend.simulation.control_selector import nx_control_selector
from edge_backend.simulation.matlab_sender import matlab_sender
from edge_backend.simulation.matlab_receiver import matlab_receiver
from edge_backend.simulation.nxmcd_client import nxmcd_client
from edge_backend.utils.logger import get_logger
from edge_backend.workers.ai_worker import AIWorker
from edge_backend.workers.gcode_sim_dispatch_worker import GcodeSimDispatchWorker
from edge_backend.workers.simulation_worker import SimulationWorker
from edge_backend.workers.sync_worker import SyncWorker

logger = get_logger("edge_backend.main_sim_only")

_CLOUD_URL = os.getenv("CLOUD_URL", "")
_pose_sync_worker: SyncWorker | None = None
_runtime_heartbeat: RuntimeStatusHeartbeat | None = None


def _runtime_snapshot() -> dict:
    ms = matlab_sender.status()
    mr = matlab_receiver.status()
    nx = nxmcd_client.status()
    return {
        "runtime": {"entrypoint": "main_sim_only", "mode": "sim_only", "alive": True},
        "connection": {
            "mongodb": {"connected": mongo_ping(), "source": "edge_mongo_ping"},
            "fluidnc": {"connected": False, "source": "disabled_in_main_sim_only", "disabled": True},
            "matlab_main": {
                "connected": False,
                "source": "disabled_in_main_sim_only",
                "reason": "main_sim_only does not represent operational MATLAB MAIN",
            },
            "sim_test": {
                "connected": True,
                "source": "main_sim_only_runtime_heartbeat",
                "matlab_sender": ms,
                "matlab_receiver": mr,
            },
            "nxmcd": {**nx, "source": "nxmcd_tcp_client"},
        },
        "dataflow": {
            "mode": "connectivity_test",
            "source_of_truth": "main_sim_only",
            "drives_nx_mcd": False,
            "owner": nx_control_selector.owner,
        },
        "gate": {
            "machine_run_allowed": False,
            "gate_enabled": False,
            "run_gcode_target": os.getenv("RUN_GCODE_TARGET", "simulation"),
            "reason": "main_sim_only never opens the machine run gate",
        },
    }


def _nx_update_from_simulation(data: dict) -> None:
    """Route MATLAB CHECK trajectory to NX MCD through the single-writer selector."""
    mode = str(data.get("mode", "")).lower().strip()
    check_id = str(data.get("check_id", "") or "manual_check")

    # Collision latch is fail-safe: late MATLAB packets from the same CHECK
    # must not re-enter CHECK mode after NX MCD has reported collision.
    if nxmcd_client.collision_handled and (not nxmcd_client.gcode_id or nxmcd_client.gcode_id == check_id):
        logger.warning("Drop MATLAB simulation packet after NX collision: check_id=%s status=%s", check_id, data.get("status"))
        return

    # MATLAB CHECK packets are allowed to drive NX MCD.
    # In simulation-only mode there is no gcode_validator to call
    # nxmcd_client.set_mode("check"), so do it here before routing.
    if mode == "check" and nxmcd_client.mode != "check":
        nxmcd_client.set_mode("check", gcode_id=check_id)

    routed = nx_control_selector.route_matlab_check(data)

    if routed and (bool(data.get("complete")) or str(data.get("status", "")).lower() in {"completed", "done"}):
        nx_control_selector.release_matlab_check()
        nxmcd_client.set_mode("idle")


def _nx_collision_stop_simulation(event: dict) -> None:
    """Stop CHECK routing, tell MATLAB bridge to reset, and keep HMI informed."""
    check_id = str(event.get("gcode_id") or "")
    logger.error(
        "NX MCD COLLISION — simulation stopped and reset requested: axes=%s check_id=%s",
        event.get("axes"),
        check_id,
    )
    try:
        nx_control_selector.collision_stop_reset(event)
    except Exception:
        logger.exception("Could not latch NXControlSelector collision state")

    try:
        matlab_sender.send_abort(check_id=check_id, reason="nxmcd_collision")
    except Exception:
        logger.exception("Could not send collision abort/reset to MATLAB bridge")


def _publish_pose_to_cloud(payload: dict) -> None:
    if _pose_sync_worker is not None:
        _pose_sync_worker.push_pose(payload)


def main() -> None:
    global _pose_sync_worker, _runtime_heartbeat

    logger.info("=" * 62)
    logger.info("🚀 CNC DIGITAL TWIN — EDGE SIMULATION ONLY")
    logger.info("=" * 62)

    if not mongo_ping():
        logger.error("❌ Không kết nối được MongoDB — thoát")
        raise SystemExit(1)
    logger.info("✅ MongoDB OK")

    db = get_db()

    sim_worker: SimulationWorker | None = None
    gcode_dispatch_worker: GcodeSimDispatchWorker | None = None
    sync_worker: SyncWorker | None = None
    ai_worker: AIWorker | None = None

    def _shutdown(signum=None, frame=None) -> None:
        global _pose_sync_worker

        logger.info("🛑 Đang tắt Edge Simulation Only...")

        if _runtime_heartbeat is not None:
            _runtime_heartbeat.stop()

        if ai_worker is not None:
            ai_worker.stop()

        if sync_worker is not None:
            sync_worker.stop()

        event_bus.unsubscribe("frontend.pose", _publish_pose_to_cloud)
        _pose_sync_worker = None

        if gcode_dispatch_worker is not None:
            gcode_dispatch_worker.stop()

        matlab_sender.stop()

        event_bus.unsubscribe("simulation.data", _nx_update_from_simulation)
        event_bus.unsubscribe("nxmcd.collision", _nx_collision_stop_simulation)
        nxmcd_client.stop()

        if sim_worker is not None:
            sim_worker.stop()

        logger.info("👋 Edge Simulation Only đã tắt")
        raise SystemExit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        sim_worker = SimulationWorker()
        sim_worker.start()
        logger.info(
            "✅ SimulationWorker started — MatlabReceiver lắng nghe port %s",
            os.getenv("MATLAB_RECV_PORT", "5001"),
        )

        matlab_sender.start()
        logger.info(
            "✅ MatlabSender started — kết nối MATLAB bridge port %s",
            os.getenv("MATLAB_SEND_PORT", "5000"),
        )

        gcode_dispatch_worker = GcodeSimDispatchWorker(
            db=db,
            matlab_sender=matlab_sender,
            poll_s=1.0,
        )
        gcode_dispatch_worker.start()
        logger.info("✅ GcodeSimDispatchWorker started — GCode_Files -> MatlabSender")

        nxmcd_client.start()
        event_bus.subscribe("simulation.data", _nx_update_from_simulation)
        event_bus.subscribe("nxmcd.collision", _nx_collision_stop_simulation)
        logger.info(
            "✅ NXMCDClient started — NX MCD server port %s | collision safety subscribed",
            os.getenv("NX_PORT", "6001"),
        )

        sync_worker = SyncWorker(cloud_base_url=_CLOUD_URL)
        _pose_sync_worker = sync_worker
        event_bus.subscribe("frontend.pose", _publish_pose_to_cloud)
        sync_worker.start()
        logger.info("✅ SyncWorker started — frontend.pose relay subscribed")

        _runtime_heartbeat = RuntimeStatusHeartbeat(
            entrypoint="main_sim_only",
            sync_worker=sync_worker,
            snapshot_factory=_runtime_snapshot,
        )
        _runtime_heartbeat.start()

        ai_worker = AIWorker()
        ai_worker.start()
        logger.info("✅ AIWorker started — Chat_Jobs/check_gcode ready")

        logger.info("=" * 62)
        logger.info("✅ Simulation-only Edge đang chạy. Không dùng FluidNC thật.")
        logger.info("   Dùng HMI/AI CHECK G-code để chạy MATLAB + NX MCD.")
        logger.info("   Ctrl+C để dừng.")
        logger.info("=" * 62)

        while True:
            time.sleep(1)

    except SystemExit:
        raise
    except Exception:
        logger.exception("❌ Edge Simulation Only lỗi trong lúc khởi động/chạy")
        _shutdown()


if __name__ == "__main__":
    main()
