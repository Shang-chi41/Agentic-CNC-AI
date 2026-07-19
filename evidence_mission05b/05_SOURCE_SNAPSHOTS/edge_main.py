"""
edge_backend/main.py
Entry point cho Edge Backend CNC Digital Twin.

Khởi động theo thứ tự:
  1. Kết nối MongoDB
  2. SensorWorker       — MQTT → normalize → DB → EventBus
  3. SimulationWorker   — MatlabReceiver lifecycle (nhận TCP port 5001 → DB → EventBus)
  4. MatlabSender       — kết nối TCP port 5000 để gửi G-code sang MATLAB
  5. NXMCDClient        — Edge → LREAL TCP → NX MCD (3D, 30Hz)
  6. TelnetCollector    — đăng ký lắng nghe telnet.status → NX MCD + MATLAB sender
  7. SyncWorker         — Edge → Cloud sync định kỳ
  8. CommandWorker      — Cloud Machine_Commands → FluidNC
  9. AIWorker           — Chat_Jobs polling → AI → execute → DB
 10. AnomalyDetector    — subscribe sensor.data → 3-tier safety check

NX MCD nhận vị trí THẬT từ FluidNC qua 2 đường:
  a) Khi STREAM mode: telnet_client._reader_thread → event_bus "telnet.status"
     → TelnetCollector._on_status() → NXControlSelector → nxmcd_client.update() (không cần poller)
  b) Khi không STREAM (Idle/Jog): NX MCD poller đọc trực tiếp fluidnc.get_status()
     (10Hz) để cập nhật liên tục ngay cả khi không có G-code chạy.

Tắt graceful khi nhận SIGINT / SIGTERM.
"""

# ruff: noqa: E402  # load_dotenv must run before singleton imports

import os
import signal
import threading
import time

from dotenv import load_dotenv

# Nạp .env trước khi import các singleton đọc cấu hình ở import-time.
load_dotenv()

from edge_backend.collectors.telnet_collector import telnet_collector
from edge_backend.communication.telnet_client import fluidnc
from edge_backend.database.mongo_client import ping as mongo_ping
from edge_backend.internal.event_bus import event_bus
from edge_backend.runtime_status import RuntimeStatusHeartbeat
from edge_backend.simulation.matlab_sender import matlab_sender
from edge_backend.simulation.matlab_receiver import matlab_receiver
from edge_backend.simulation.nxmcd_client import nxmcd_client
from edge_backend.simulation.control_selector import nx_control_selector
from edge_backend.utils.logger import get_logger
from edge_backend.workers.ai_worker import AIWorker
from edge_backend.workers.command_worker import CommandWorker
from edge_backend.workers.sensor_worker import SensorWorker
from edge_backend.workers.simulation_worker import SimulationWorker
from edge_backend.workers.sync_worker import SyncWorker

logger = get_logger("edge_backend.main")

# NX MCD poller — đọc MPos/FS khi KHÔNG có STREAM mode đang chạy.
# Khi STREAM mode active, TelnetCollector đã lo (qua event_bus), không cần poll.
_NX_POLL_INTERVAL = 0.1  # 10Hz
_nx_poll_running  = False
_nx_poll_thread   = None


def _nx_poll_from_fluidnc() -> None:
    """Đọc MPos + FS trực tiếp từ FluidNC (Idle/Jog mode) → NX MCD.

    Bỏ qua khi FluidNC đang STREAM mode vì TelnetCollector xử lý rồi,
    tránh gửi trùng / xung đột dữ liệu.
    """
    while _nx_poll_running:
        try:
            # Bỏ qua khi STREAM hoặc CHECK mode. Trong CHECK, dữ liệu quỹ đạo
            # MATLAB sở hữu NX MCD; poll MPos thật sẽ làm ghi đè mô phỏng.
            if fluidnc.is_streaming or nxmcd_client.mode == "check" or nx_control_selector.owner == "matlab_check":
                time.sleep(_NX_POLL_INTERVAL)
                continue

            status = fluidnc.get_status()  # {state, x, y, z, feed, spindle}
            if status.get("state") != "unknown":
                nx_control_selector.route_fluidnc_status(status, streaming=False)
        except Exception as e:
            logger.debug(f"NX poll FluidNC lỗi: {e}")
        time.sleep(_NX_POLL_INTERVAL)




def _nx_update_from_simulation(data: dict) -> None:
    """Đưa quỹ đạo MATLAB CHECK sang NX MCD qua Control Selector."""
    nx_control_selector.route_matlab_check(data)

_CLOUD_URL = os.getenv("CLOUD_URL", "")
_pose_sync_worker = None
_runtime_heartbeat = None


def _dataflow_from_owner(owner: str) -> dict:
    if owner == "matlab_check":
        return {"mode": "pre_run_check", "source_of_truth": "matlab_simulink", "drives_nx_mcd": True}
    if owner == "stream_fluidnc":
        return {"mode": "machine_run", "source_of_truth": "fluidnc_mpos", "drives_nx_mcd": True}
    if owner == "idle_fluidnc":
        return {"mode": "manual_jog_or_direct_line", "source_of_truth": "fluidnc_mpos", "drives_nx_mcd": True}
    if owner == "home_sync":
        return {"mode": "home_sync", "source_of_truth": "fluidnc_home_pose", "drives_nx_mcd": True}
    if owner == "estop":
        return {"mode": "estop", "source_of_truth": "collision_latch", "drives_nx_mcd": True}
    return {"mode": "idle", "source_of_truth": "unknown", "drives_nx_mcd": False}


def _runtime_snapshot() -> dict:
    selector = nx_control_selector.snapshot()
    owner = selector.get("owner", "unknown")
    ms = matlab_sender.status()
    mr = matlab_receiver.status()
    nx = nxmcd_client.status()
    fluid = fluidnc.connection_status()
    return {
        "runtime": {"entrypoint": "main", "mode": "machine", "alive": True},
        "connection": {
            "mongodb": {"connected": mongo_ping(), "source": "edge_mongo_ping"},
            "fluidnc": {**fluid, "source": "fluidnc_telnet_socket"},
            "matlab_main": {
                "connected": bool(ms.get("connected")),
                "source": "matlab_sender_socket",
                "sender": ms,
                "receiver": mr,
            },
            "sim_test": {"connected": False, "source": "main_sim_only_heartbeat", "disabled_in": "main"},
            "nxmcd": {**nx, "source": "nxmcd_tcp_client"},
        },
        "dataflow": {**_dataflow_from_owner(owner), "owner": owner, "selector": selector},
        "gate": {
            "machine_run_allowed": False,
            "gate_enabled": os.getenv("RUN_PERMISSION_GATE", "0").strip().lower() in {"1", "true", "yes", "on"},
            "run_gcode_target": os.getenv("RUN_GCODE_TARGET", "simulation"),
            "reason": "Per-G-code gate is evaluated by Cloud/Edge run_gcode command",
        },
    }


def _publish_pose_to_cloud(payload: dict) -> None:
    if _pose_sync_worker is not None:
        _pose_sync_worker.push_pose(payload)



def main() -> None:
    global _pose_sync_worker, _runtime_heartbeat, _nx_poll_running, _nx_poll_thread

    logger.info("=" * 55)
    logger.info("🚀  CNC DIGITAL TWIN — EDGE BACKEND")
    logger.info("=" * 55)

    # 1. MongoDB
    if not mongo_ping():
        logger.error("❌ Không kết nối được MongoDB — thoát")
        raise SystemExit(1)
    logger.info("✅ MongoDB OK")

    # 2. SensorWorker (MQTT → DB → EventBus)
    sensor_worker = SensorWorker()
    sensor_worker.start()
    logger.info("✅ SensorWorker started")

    # 3. SimulationWorker (MatlabReceiver lifecycle — nhận TCP 5001 → DB → EventBus)
    sim_worker = SimulationWorker()
    sim_worker.start()
    logger.info("✅ SimulationWorker started (MatlabReceiver lắng nghe port 5001)")

    # 4. MatlabSender (gửi G-code → MATLAB port 5000)
    matlab_sender.start()
    logger.info("✅ MatlabSender started (kết nối port 5000)")

    # 5. NX MCD (Edge → Control Selector → LREAL 30Hz)
    nxmcd_client.start()
    event_bus.subscribe("simulation.data", _nx_update_from_simulation)
    logger.info("✅ NXMCDClient started + Control Selector bridge subscribed")

    # 6. TelnetCollector (đăng ký lắng nghe telnet.status → NX MCD + MATLAB)
    telnet_collector.connect()
    logger.info("✅ TelnetCollector connected (STREAM mode ready)")

    # 7. SyncWorker (Edge → Cloud)
    sync_worker = SyncWorker(cloud_base_url=_CLOUD_URL)
    _pose_sync_worker = sync_worker
    event_bus.subscribe("frontend.pose", _publish_pose_to_cloud)
    sync_worker.start()
    logger.info("✅ SyncWorker started + frontend.pose relay subscribed")

    _runtime_heartbeat = RuntimeStatusHeartbeat(
        entrypoint="main",
        sync_worker=sync_worker,
        snapshot_factory=_runtime_snapshot,
    )
    _runtime_heartbeat.start()

    # 8. CommandWorker (Cloud Machine_Commands -> FluidNC)
    command_worker = CommandWorker(cloud_base_url=_CLOUD_URL)
    command_worker.start()
    logger.info("✅ CommandWorker started")

    # 9. AIWorker (Chat_Jobs polling)
    ai_worker = AIWorker()
    ai_worker.start()
    logger.info("✅ AIWorker started")

    # 10. Anomaly Detector (subscribe sensor.data)
    try:
        from edge_backend.ai.anomaly_detector import on_sensor_data
        event_bus.subscribe("sensor.data", on_sensor_data)
        logger.info("✅ AnomalyDetector subscribed to sensor.data")
    except Exception as e:
        logger.warning(f"⚠️  AnomalyDetector không load được: {e}")

    # NX MCD poller — chạy khi không có STREAM mode (Idle/Jog)
    _nx_poll_running = True
    _nx_poll_thread = threading.Thread(
        target=_nx_poll_from_fluidnc, name="NXPollFluidNC", daemon=True
    )
    _nx_poll_thread.start()
    logger.info("✅ NX MCD poller (FluidNC MPos/FS, non-stream) started")

    logger.info("=" * 55)
    logger.info("✅ Tất cả services đã khởi động — đang chạy (Ctrl+C để dừng)")
    logger.info("=" * 55)

    # Graceful shutdown
    def _shutdown(signum, frame):
        logger.info("🛑 Nhận tín hiệu dừng, đang tắt...")
        _nx_poll_running = False
        if _nx_poll_thread:
            _nx_poll_thread.join(timeout=2)

        if _runtime_heartbeat is not None:
            _runtime_heartbeat.stop()

        telnet_collector.disconnect()
        command_worker.stop()
        ai_worker.stop()
        sync_worker.stop()
        event_bus.unsubscribe("frontend.pose", _publish_pose_to_cloud)
        matlab_sender.stop()      # thay matlab_client.stop()
        event_bus.unsubscribe("simulation.data", _nx_update_from_simulation)
        nxmcd_client.stop()
        sim_worker.stop()         # cascade → matlab_receiver.stop()
        sensor_worker.stop()

        logger.info("👋 Edge Backend đã tắt")
        raise SystemExit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()