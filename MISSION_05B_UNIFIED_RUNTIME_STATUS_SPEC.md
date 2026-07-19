# Mission 05B — Unified Runtime & System Status Contract

## Goal
Làm lại tận gốc phần đồng bộ trạng thái hệ thống giữa frontend, cloud_backend, edge_backend, `main.py`, `main_sim_only.py` và env/run scripts.

## Problem
Các bản 05A.x còn vá theo triệu chứng: dot frontend, Simulation_Data, main_sim_only heartbeat. Điều này làm lẫn 4 khái niệm:

1. CONNECTION — dịch vụ/socket/ping đang kết nối hay không.
2. RUNTIME — entrypoint nào đang sống: `main.py` hay `main_sim_only.py`.
3. DATAFLOW — dữ liệu đang đi theo `pre_run_check`, `machine_run`, `manual_jog_or_direct_line`, `connectivity_test`.
4. GATE — có được phép chạy máy thật hay không.

## Expected behavior
- `MATLAB MAIN` sáng khi `main.py` báo socket Edge→MATLAB bridge đang connected.
- `SIM TEST` sáng khi `main_sim_only.py` đang sống qua runtime heartbeat.
- `FluidNC` sáng khi `main.py` báo FluidNC Telnet socket connected.
- `NX MCD` sáng khi runtime báo NX MCD TCP client connected.
- `MongoDB` sáng khi Cloud `mongo_ping()` OK.
- Frontend chỉ đọc một contract: `GET /api/system/status`.
- Không dùng `Simulation_Data` làm nguồn duy nhất cho service CONNECTION.
- Machine run vẫn bị khóa bởi Mission 05A.1 gate: CHECK PASS → approved → Confirm → confirmed.

## Non-goals
- Không thay đổi logic planner/Axis1D/NX frame Mission 04B.
- Không nới lỏng machine run gate.
- Không cố xác nhận real MATLAB/NX/FluidNC trong sandbox.

## Acceptance criteria
- [x] Có `Runtime_Status` heartbeat từ cả `main.py` và `main_sim_only.py`.
- [x] Có endpoint `GET /api/system/status` trả `runtime`, `connection`, `dataflow`, `gate`.
- [x] Frontend đọc `/api/system/status`, không tự suy luận từ nhiều API cũ.
- [x] Env profile tách machine và sim_only.
- [x] Run scripts tách `RUN_70_MAIN_MACHINE` và `RUN_71_MAIN_SIM_ONLY`.
- [x] Sandbox compile/test pass.
- [ ] User kiểm chứng real MATLAB/NX/FluidNC trên máy thật.
