"""Self-contained full-loop protocol test, no MATLAB/NX required.

It verifies the critical path:
  Edge MatlabSender -> fake MATLAB bridge server :5000
  fake MATLAB simulator -> Edge MatlabReceiver :5001
  Edge ControlSelector -> NXMCDClient :6001
  fake NX MCD client reads 12 big-endian LREAL values

Do NOT run this while the real Edge is already using ports 5000/5001/6001.
This is for an isolated VS Code terminal test.
"""
from __future__ import annotations

import json
import os
import socket
import struct
import sys
import threading
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# This protocol self-test should be runnable in a clean sandbox even when
# database packages such as pymongo/bson are not installed yet. The real
# Edge runtime still uses MongoDB; this fake repository only prevents the
# isolated mock test from failing before it reaches the TCP/NX protocol path.
class _InMemorySimulationRepo:
    def __init__(self) -> None:
        self.records: list[dict] = []

    def save_virtual_data(self, data: dict) -> str:
        self.records.append(dict(data))
        return f"mock-sim-{len(self.records)}"

    def get_latest_virtual(self) -> dict | None:
        return self.records[-1] if self.records else None

    def get_virtual_history(self, minutes: int = 10) -> list[dict]:
        return list(self.records)

    def get_unsynced_virtual(self, limit: int = 20) -> list[dict]:
        return list(self.records[-limit:])

    def mark_virtual_synced(self, ids: list[str]) -> int:
        return len(ids)


_fake_sim_repo_module = types.ModuleType("edge_backend.database.repositories.simulation_repo")
_fake_sim_repo_module.simulation_repo = _InMemorySimulationRepo()
sys.modules.setdefault("edge_backend.database.repositories.simulation_repo", _fake_sim_repo_module)

# Set env before importing edge singletons.
os.environ.setdefault("MATLAB_IP", "127.0.0.1")
os.environ.setdefault("MATLAB_SEND_PORT", "5000")
os.environ.setdefault("MATLAB_RECV_PORT", "5001")
os.environ.setdefault("NX_HOST", "127.0.0.1")
os.environ.setdefault("NX_PORT", "6001")
os.environ.setdefault("NXMCD_SEND_HZ", "30")
os.environ.setdefault("NXMCD_SEND_ONLY_ON_CHANGE", "0")
os.environ.setdefault("NX_SELECTOR_MIN_UPDATE_S", "0.0")

from edge_backend.internal.event_bus import event_bus
from edge_backend.simulation.control_selector import nx_control_selector
from edge_backend.simulation.matlab_receiver import matlab_receiver
from edge_backend.simulation.matlab_sender import matlab_sender
from edge_backend.simulation.nxmcd_client import nxmcd_client

GCODE = """G21
G90
G0 X0 Y0 Z5
G1 X30 Y10 Z0 F400
G1 X0 Y0 Z0 F400
M30
"""


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("socket closed")
        buf += chunk
    return buf


def _pack_json(payload: dict) -> bytes:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return struct.pack("<I", len(body)) + body


def fake_matlab_server(stop: threading.Event, accepted: threading.Event, sent_done: threading.Event) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 5000))
        server.listen(1)
        server.settimeout(10)
        conn, _ = server.accept()
        accepted.set()
        with conn:
            header = _recv_exact(conn, 4)
            size = struct.unpack("<I", header)[0]
            body = _recv_exact(conn, size)
            req = json.loads(body.decode("utf-8"))
            check_id = str(req.get("check_id", "mock-check"))
            packet_id = str(req.get("packet_id", ""))
            # Connect as MATLAB -> Edge receiver :5001
            deadline = time.time() + 5
            out = None
            while time.time() < deadline and out is None:
                try:
                    out = socket.create_connection(("127.0.0.1", 5001), timeout=1)
                except OSError:
                    time.sleep(0.05)
            if out is None:
                raise RuntimeError("cannot connect to Edge MatlabReceiver :5001")
            with out:
                # 30 Hz-ish path samples. These mimic bridge JSON packets from CNC3 frames.
                # Keep the peak setpoint for several packets so the 30 Hz NX
                # sender cannot miss it due to thread scheduling jitter.
                samples = [
                    (0.0, 0.0, 5.0, 0.0),
                    (5.0, 1.7, 4.2, 0.2),
                    (15.0, 5.0, 2.5, 0.5),
                    (30.0, 10.0, 0.0, 0.70),
                    (30.0, 10.0, 0.0, 0.75),
                    (30.0, 10.0, 0.0, 0.80),
                    (30.0, 10.0, 0.0, 0.85),
                    (20.0, 6.7, 0.0, 0.9),
                    (10.0, 3.3, 0.0, 0.95),
                    (0.0, 0.0, 0.0, 1.0),
                ]
                last = samples[0]
                for i, (x, y, z, progress) in enumerate(samples, start=1):
                    px, py, pz, _ = last
                    vx = (x - px) * 30.0
                    vy = (y - py) * 30.0
                    vz = (z - pz) * 30.0
                    payload = {
                        "protocol": "matlab-edge-json-v1",
                        "packet_id": packet_id,
                        "sequence": i,
                        "mode": "check",
                        "check_id": check_id,
                        "position": {"x": x, "y": y, "z": z},
                        "velocity": {"x": vx, "y": vy, "z": vz},
                        "acceleration": {"x": 10.0 if i < 4 else 0.0, "y": 4.0 if i < 4 else 0.0, "z": 2.0 if i < 4 else 0.0},
                        "deceleration": {"x": 0.0 if i < 4 else 10.0, "y": 0.0 if i < 4 else 4.0, "z": 0.0 if i < 4 else 2.0},
                        "torque": {"x": 0.0, "y": 0.0, "z": 0.0},
                        "gcode": "mock trajectory",
                        "progress": progress,
                        "complete": progress >= 1.0,
                        "success": True,
                        "status": "completed" if progress >= 1.0 else "running",
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                        "matlab_sent_at_epoch": time.time(),
                    }
                    out.sendall(_pack_json(payload))
                    last = (x, y, z, progress)
                    time.sleep(1.0 / 30.0)
            sent_done.set()
            while not stop.is_set():
                time.sleep(0.05)


def fake_nx_client(stop: threading.Event, frames: list[tuple[float, ...]]) -> None:
    deadline = time.time() + 5
    sock = None
    while time.time() < deadline and sock is None:
        try:
            sock = socket.create_connection(("127.0.0.1", 6001), timeout=1)
        except OSError:
            time.sleep(0.05)
    if sock is None:
        raise RuntimeError("cannot connect to Edge NXMCDClient :6001")
    with sock:
        sock.settimeout(0.5)
        while not stop.is_set():
            try:
                data = _recv_exact(sock, 96)
                vals = struct.unpack(">" + "d" * 12, data)
                frames.append(vals)
                feedback = struct.pack(">" + "d" * 12, *([0.0] * 12)) + b"\x00\x00\x00\x00"
                sock.sendall(feedback)
            except socket.timeout:
                continue
            except Exception:
                break


def main() -> int:
    stop = threading.Event()
    matlab_accepted = threading.Event()
    matlab_sent_done = threading.Event()
    nx_frames: list[tuple[float, ...]] = []

    event_bus.subscribe("simulation.data", nx_control_selector.route_matlab_check)
    matlab_receiver.start()
    nxmcd_client.start()
    nxmcd_client.set_mode("check", gcode_id="mock-gcode")

    threads = [
        threading.Thread(target=fake_matlab_server, args=(stop, matlab_accepted, matlab_sent_done), daemon=True),
        threading.Thread(target=fake_nx_client, args=(stop, nx_frames), daemon=True),
    ]
    for t in threads:
        t.start()

    matlab_sender.start()
    deadline = time.time() + 10
    ok = False
    while time.time() < deadline:
        ok = matlab_sender.send_check(GCODE, check_id="mock-check")
        if ok:
            break
        time.sleep(0.1)
    if not ok:
        raise AssertionError("MatlabSender could not send to fake MATLAB")

    if not matlab_sent_done.wait(timeout=8):
        raise AssertionError("fake MATLAB did not finish sending simulation packets")

    time.sleep(1.0)
    stop.set()
    matlab_sender.stop()
    nxmcd_client.set_mode("idle")
    nxmcd_client.stop()
    matlab_receiver.stop()
    event_bus.unsubscribe("simulation.data", nx_control_selector.route_matlab_check)

    if len(nx_frames) < 5:
        raise AssertionError(f"Expected >=5 NX frames, got {len(nx_frames)}")
    xs = [f[0] for f in nx_frames]
    ys = [f[4] for f in nx_frames]
    zs = [f[8] for f in nx_frames]
    if max(xs) < 25.0 or max(ys) < 8.0:
        raise AssertionError(f"NX frames did not carry motion: maxX={max(xs):.3f}, maxY={max(ys):.3f}")
    if any(not (-1000 < v < 1000) for frame in nx_frames for v in frame):
        raise AssertionError("NX frame has unreasonable numeric value")

    print("PASS full-loop mock selftest")
    print(f"  NX frames received: {len(nx_frames)}")
    print(f"  max X/Y/Z: {max(xs):.3f}, {max(ys):.3f}, {max(zs):.3f}")
    print("  path tested: Edge sender -> fake MATLAB -> Edge receiver -> ControlSelector -> NX 12 LREAL")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAIL full-loop mock selftest: {exc}", file=sys.stderr)
        raise
