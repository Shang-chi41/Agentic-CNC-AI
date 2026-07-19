# Mission 05B.2 — True Connection Contract + Simulation Run Separation

## Goal
Sửa tận gốc lỗi đồng bộ trạng thái hệ thống theo kiến trúc người dùng chốt:

- `main_sim_only` là runtime test/mô phỏng, không bị chặn bởi machine G-code gate.
- `main.py` là runtime vận hành chính; chỉ đường chạy máy thật bằng FluidNC mới cần safety gate.
- SYSTEM CONNECTION chỉ phản ánh kết nối/sống chết của từng service/device, không phản ánh CHECK PASS, MACHINE_NX_SYNCED hay run permission.

## Key behavior after patch

### SYSTEM CONNECTION
- FluidNC sáng khi `main.py` có kết nối Telnet FluidNC thật.
- MATLAB MAIN sáng khi Edge có kết nối MATLAB bridge thật qua `MatlabSender`, hoặc vừa nhận packet MATLAB gần đây qua `MatlabReceiver`.
- SIM TEST sáng khi `main_sim_only` runtime heartbeat còn fresh.
- NX MCD sáng khi `NXMCDClient` có TCP client thật kết nối vào Edge.
- MongoDB sáng khi Cloud `mongo_ping()` OK.

### G-code run policy
- `main_sim_only` / `RUN_GCODE_TARGET=simulation`: `/api/control/run/{gcode_id}` đưa G-code vào simulation queue, không yêu cầu CHECK PASS/Confirm, không gửi Machine_Commands chạy máy thật.
- `main.py` / `RUN_GCODE_TARGET=machine`: vẫn bắt buộc CHECK PASS → approved → Confirm → confirmed → machine gate.

## Main files changed
- `cloud_backend/routes/system_routes.py`
- `cloud_backend/routes/control_routes.py`
- `edge_backend/main.py`
- `edge_backend/main_sim_only.py`
- `edge_backend/simulation/matlab_sender.py`
- `edge_backend/simulation/matlab_receiver.py`
- `edge_backend/communication/telnet_client.py`
- `edge_backend/workers/gcode_sim_dispatch_worker.py`
- `frontend/js/control.js`
- `.env.example`, `config/.env.machine.example`, `config/.env.sim_only.example`
- `integration_tests/test_mission05b2_architecture_regression_static.py`

## Verification
- `python -m compileall edge_backend cloud_backend`: PASS
- `node --check frontend/js/control.js`: PASS
- `node --check frontend/js/monitor.js`: PASS
- `python -m pytest integration_tests -q`: PASS — 98 tests

## Not verified in sandbox
- Real MATLAB bridge socket on the user's machine.
- Real NX MCD TCP client connection.
- Real FluidNC Telnet connection.
- Browser UI color change against running local Cloud/Edge.
