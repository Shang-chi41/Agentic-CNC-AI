# Mission 05A.3 — main.py vs main_sim_only Frontend Sync

## Problem fixed
Frontend SYSTEM CONNECTION chưa phản ánh đúng 2 chế độ:

- `main_sim_only` = test connectivity only.
- `main.py` = runtime vận hành cho:
  - `pre_run_check`
  - `machine_run`
  - `manual_jog_or_direct_line`

Mission 05A.2 đã không tính `connectivity_test` là MATLAB MAIN, nhưng frontend chưa có dot riêng cho SIM TEST và base inline script vẫn đọc object response sai.

## Backend changes
`cloud_backend/routes/monitor_routes.py` now returns:

```json
{
  "fluidnc": {},
  "matlab": {},
  "nxmcd": {},
  "sim_test": {},
  "mongodb": {}
}
```

Rules:
- `matlab` / MATLAB MAIN: only fresh `Simulation_Data` with
  `simulation_phase in ["pre_run_check", "machine_stream_observer", "machine_run"]`.
- `sim_test`: only fresh `Simulation_Data` with
  `simulation_phase = "connectivity_test"`.
- `nxmcd`: fresh `drives_nx_mcd = true`.
- `main_sim_only` does not imply MATLAB MAIN online and does not open the G-code machine-run gate.

## Frontend changes
- `base.html`
  - Renamed MATLAB → MATLAB MAIN.
  - Added SIM TEST row in CONNECTION panel.
  - Added SIM TEST item in SYSTEM CONNECTION panel.
  - Fixed connection parser to handle object response: `{connected, status, age_s}`.
- `monitor.html`
  - Added SIM TEST dot in the right connection strip.
- `monitor.js`
  - Added `fetchConnectionStatus()`.
  - Updates Edge / MATLAB MAIN / SIM TEST / NX MCD / MongoDB dots.

## Safety gate behavior
No relaxation of Mission 05A.1 machine-run gate:
- `main_sim_only` connectivity test is separate from full G-code machine run.
- `main.py + machine run` remains blocked until CHECK PASS → approved → Confirm → confirmed.

## Verification
- `python -m compileall cloud_backend edge_backend`: PASS
- `node --check frontend/js/monitor.js`: PASS
- `node --check frontend/js/control.js`: PASS
- `python -m pytest integration_tests -q`: PASS — 78 tests

## Runtime note
Sandbox cannot prove real MATLAB/NX/FluidNC dot behavior. Verify locally:
1. Run `main_sim_only` → SIM TEST should light; MATLAB MAIN should stay off unless operational phases exist.
2. Run `main.py` CHECK → MATLAB MAIN lights.
3. Run real machine stream → machine gate still requires confirmed G-code.
