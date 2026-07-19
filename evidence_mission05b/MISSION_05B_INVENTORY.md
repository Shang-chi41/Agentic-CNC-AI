# Mission 05B Inventory

## Entry points
- `edge_backend/main.py`: runtime chính cho CHECK/RUN/JOG/direct line.
- `edge_backend/main_sim_only.py`: runtime test connectivity, không dùng FluidNC thật.
- `cloud_backend/main.py`: FastAPI Cloud/HMI backend.

## Frontend consumers
- `frontend/pages/base.html`: CONNECTION và SYSTEM CONNECTION.
- `frontend/pages/monitor.html`: right connection strip.
- `frontend/js/monitor.js`: monitor connection strip updater.
- `frontend/js/control.js`: G-code run workflow and gate checks.

## Cloud APIs
- Existing: `/api/monitor/connection`, now backward-compatible wrapper.
- New source of truth: `/api/system/status`.
- New Edge sync endpoint: `/api/sync/runtime_status`.

## Edge producers
- `edge_backend/runtime_status.py`: shared RuntimeStatusHeartbeat.
- `edge_backend/main.py`: pushes entrypoint=`main` runtime status.
- `edge_backend/main_sim_only.py`: pushes entrypoint=`main_sim_only` runtime status.

## Service status sources
- MATLAB MAIN: `matlab_sender.status()` from Edge→MATLAB bridge socket.
- SIM TEST: fresh `main_sim_only` runtime heartbeat.
- FluidNC: `fluidnc.connection_status()`.
- NX MCD: `nxmcd_client.status()` from TCP client state.
- MongoDB: Cloud `mongo_ping()`.

## Env profiles
- `config/.env.machine.example`
- `config/.env.sim_only.example`
- `.env.example` updated with runtime contract variables.

## Run scripts
- `RUN_70_MAIN_MACHINE.bat` / `scripts/RUN_70_MAIN_MACHINE.ps1`
- `RUN_71_MAIN_SIM_ONLY.bat` / `scripts/RUN_71_MAIN_SIM_ONLY.ps1`
