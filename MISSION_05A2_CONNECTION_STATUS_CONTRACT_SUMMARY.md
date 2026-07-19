# Mission 05A.2 — Fix `/api/monitor/connection` Contract

## Problem
Frontend SYSTEM CONNECTION dots were reading Cloud `/api/monitor/connection`, but the backend still queried old fields:
- `matlab_results`
- `nxmcd_synced_at`

Those fields are no longer written after Mission 05A/05A.1. The active contract is:
- `simulation_phase`
- `drives_nx_mcd`

## Fix
Changed `cloud_backend/routes/monitor_routes.py::connection_status()` only.

### MATLAB status
Connected only when a recent `Simulation_Data` record exists with:

```python
simulation_phase in ["pre_run_check", "machine_stream_observer", "machine_run"]
```

This deliberately excludes `connectivity_test`, because `main_sim_only` is a connectivity-test mode, not the real operational `main.py` mode.

### NX MCD status
Connected when a recent `Simulation_Data` record exists with:

```python
drives_nx_mcd == True
```

## Preserved
- Response shape unchanged:
  - `fluidnc`
  - `matlab`
  - `nxmcd`
  - `mongodb`
- Frontend does not need another API-shape change.
- FluidNC and MongoDB logic unchanged.
- `matlab_receiver.py` and `sync_worker.py` untouched.

## Files changed
- `cloud_backend/routes/monitor_routes.py`
- `integration_tests/test_monitor_connection_contract_mission05a2.py`

## Verification
- `python -m compileall cloud_backend`: PASS
- `python -m pytest integration_tests/test_monitor_connection_contract_mission05a2.py -q`: PASS — 5 tests
- `python -m pytest integration_tests/test_mission05a1_safety_gate_static.py -q`: PASS — 6 tests
- `python -m pytest integration_tests -q`: PASS — 74 tests

## Limitation
Sandbox did not run real MATLAB / NX MCD / FluidNC. The HMI dot color must still be confirmed on the real runtime.
