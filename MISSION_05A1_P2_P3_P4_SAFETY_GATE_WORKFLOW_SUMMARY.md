# Mission 05A.1 — P2/P3/P4 Safety Gate + Data Separation + HMI Workflow

## Completed

### P2 — Khóa safety gate trước khi chạy máy thật
- `confirm_gcode` chỉ cho `approved -> confirmed`.
- Không cho `needs_check`, `pending_validation`, `pending_confirmation` confirm thẳng.
- `/api/control/run/{gcode_id}` chỉ queue nếu G-code đã `confirmed` từ `approved`.
- Cloud sync command poll chặn `run_gcode` command không có `run_authorization`.
- Edge CommandWorker từ chối Cloud G-code không có `machine_run_authorized=true`, không được confirm từ `approved`, hoặc checksum khác bản đã approved.

### P3 — Tách dữ liệu CHECK / RUN / connectivity-test
- MATLAB receiver gắn contract:
  - `simulation_phase`
  - `source_of_truth`
  - `drives_nx_mcd`
  - `dataflow_mode`
  - `gcode_id`
  - `line_index`
- Edge và Cloud duplicate data theo phase collection:
  - `Simulation_Check_Data`
  - `Simulation_Stream_Observer`
  - `Simulation_Machine_Run`
  - `Simulation_Connectivity_Test`

### P4 — Chuẩn hóa HMI workflow
- G-code mới lưu ở `needs_check`.
- Nút Confirm chỉ hiện khi `approved`.
- Nút Run chỉ hiện khi `confirmed`.
- RUN ALL không chọn `queued` nữa.
- Frontend run gate không còn bypass `return true`; kiểm tra `/api/pose/latest` trước khi cho Run.

## Verification
- `python -m compileall edge_backend cloud_backend`: PASS
- `node --check frontend/js/control.js`: PASS
- `node --check frontend/js/monitor.js`: PASS
- `node --check frontend/js/hmi_state_presenter_v5.js`: PASS
- `python -m pytest integration_tests -q`: PASS — 69 tests

## Limitation
Sandbox verified code/static/unit/mock only. Real MATLAB/FluidNC/NX MCD runtime still needs local verification.
