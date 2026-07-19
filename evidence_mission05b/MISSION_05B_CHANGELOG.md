# Mission 05B Changelog

## Added
- `edge_backend/runtime_status.py`
- `cloud_backend/routes/system_routes.py`
- `/api/sync/runtime_status`
- `/api/system/status`
- `config/.env.machine.example`
- `config/.env.sim_only.example`
- `RUN_70_MAIN_MACHINE.bat`
- `RUN_71_MAIN_SIM_ONLY.bat`
- Mission 05B static tests.

## Changed
- `edge_backend/main.py`: pushes `main` runtime heartbeat.
- `edge_backend/main_sim_only.py`: pushes `main_sim_only` runtime heartbeat, no longer uses `Simulation_Data` as SIM TEST source of truth.
- `edge_backend/workers/sync_worker.py`: immediate runtime status push.
- `matlab_sender`, `matlab_receiver`, `nxmcd_client`, `telnet_client`: service-level status snapshots.
- `cloud_backend/routes/monitor_routes.py`: backward-compatible `/api/monitor/connection` now delegates to unified status.
- `frontend/pages/base.html`, `frontend/js/monitor.js`: read `/api/system/status`.

## Preserved
- Mission 05A.1 safety gate remains active.
- Mission 04B Axis1D/NX frame logic untouched.
