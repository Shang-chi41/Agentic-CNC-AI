# Mission 05A — Dataflow Contract Lock

## Mục tiêu
Khóa rõ 4 mode dữ liệu chính cho HMI/Edge/NX MCD:

1. `pre_run_check`
2. `machine_run`
3. `manual_jog_or_direct_line`
4. `connectivity_test`

## Thay đổi chính
- Edge Control Selector enrich pose payload với:
  - `dataflow_mode`
  - `simulation_phase`
  - `source_of_truth`
  - `drives_nx_mcd`
- Cloud pose relay có default fields cho dataflow contract.
- Frontend Monitor thay cụm trạng thái lặp `SYNC / OWNER / CHECK / RUN` bằng 4 oval mode indicators:
  - `CHECK`
  - `MACHINE RUN`
  - `JOG / 1 LINE`
  - `CONNECT TEST`
- Vẫn giữ banner trên cùng cho `RUN / SYNC / CHECK`, còn cụm ở top bar nay chỉ tập trung vào **mode đang active**.

## Quy tắc hiển thị
- `matlab_check` → `pre_run_check`
- `stream_fluidnc` → `machine_run`
- `idle_fluidnc` → `manual_jog_or_direct_line`
- `test_only` hoặc `simulation_phase=connectivity_test` → `connectivity_test`

## File sửa
- `edge_backend/simulation/control_selector.py`
- `cloud_backend/routes/pose_routes.py`
- `frontend/pages/monitor.html`
- `frontend/css/monitor.css`
- `frontend/js/monitor.js`
- `frontend/js/hmi_state_presenter_v5.js`

## Lưu ý
Patch này chưa đổi logic gate chạy máy thật; nó khóa **contract hiển thị và ownership mode** trước, phù hợp Mission 05A.
