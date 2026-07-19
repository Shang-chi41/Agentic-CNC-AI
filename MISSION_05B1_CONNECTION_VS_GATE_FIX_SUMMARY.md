# Mission 05B.1 — Connection vs Gate Contract Fix

## Problem corrected
The previous frontend gate code mixed simulation/connectivity tests with the real machine run gate:

```js
const runReady = run_permission === 'READY';
const syncReady = sync_status === 'MACHINE_NX_SYNCED';
const checkReady = check_status === 'PASSED';
```

That is wrong for simulation/connectivity. SIM/main_sim_only is a test/runtime-liveness mode and must not require CHECK PASS or MACHINE_NX_SYNCED.

## Contract now enforced

### Connection
- MATLAB MAIN lights from MATLAB service connection: sender socket connected OR at least one MATLAB packet received.
- SIM TEST lights from main_sim_only runtime heartbeat.
- FluidNC lights from FluidNC connection.
- NX MCD lights from NX MCD client socket.
- MongoDB lights from Cloud Mongo ping.

### Gate
- Simulation/main_sim_only bypasses machine-only gate.
- Real machine target uses backend source of truth only: `gate.machine_run_allowed`.
- Frontend no longer recomputes machine readiness from `run_permission`, `sync_status`, and `check_status`.

## Files changed
- `frontend/js/control.js`
- `edge_backend/main.py`
- `edge_backend/main_sim_only.py`
- `cloud_backend/routes/system_routes.py`
- tests updated/added under `integration_tests/`

## Verification
- `python -m compileall cloud_backend edge_backend`: PASS
- `node --check frontend/js/control.js`: PASS
- `node --check frontend/js/monitor.js`: PASS
- `python -m pytest integration_tests -q`: PASS — 91 tests

## Runtime limitation
Sandbox did not connect to real MATLAB / NX MCD / FluidNC. Runtime dots must be confirmed on the user's machine.
