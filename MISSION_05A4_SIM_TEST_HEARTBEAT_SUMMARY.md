# Mission 05A.4 — SIM TEST Heartbeat for main_sim_only

## Problem observed
User ran:

```powershell
.\.venv\Scripts\python.exe -m edge_backend.main_sim_only
```

but the HMI SYSTEM CONNECTION still showed:

- SIM TEST: `no_data`

Root cause:
- Mission 05A.3 added a separate `sim_test` connection key in Cloud/frontend.
- But `main_sim_only.py` did not write any `Simulation_Data` heartbeat with
  `simulation_phase="connectivity_test"` by itself.
- Therefore `/api/monitor/connection` had nothing to read for `sim_test` until a separate MATLAB packet arrived and was synced.

## Fix
Added a main_sim_only connectivity heartbeat:

```text
edge_backend.main_sim_only
→ every SIM_ONLY_HEARTBEAT_S seconds, default 5s
→ writes Simulation_Data:
   simulation_phase = connectivity_test
   dataflow_mode = connectivity_test
   source_of_truth = main_sim_only
   drives_nx_mcd = false
   test_only = true
→ immediately pushes that record to Cloud through SyncWorker.push_simulation_record()
```

## Files changed
- `edge_backend/main_sim_only.py`
- `edge_backend/workers/sync_worker.py`
- `integration_tests/test_mission05a4_sim_only_heartbeat_static.py`

## Behavior now
- `main_sim_only` lights only SIM TEST.
- `main_sim_only` does not light MATLAB MAIN.
- `main_sim_only` does not open the G-code machine-run safety gate.
- `main.py` remains the runtime for CHECK/RUN/JOG/direct-line.
- Machine-run G-code remains blocked until CHECK PASS → approved → Confirm → confirmed.

## Verification
- `python -m compileall cloud_backend edge_backend`: PASS
- `node --check frontend/js/monitor.js`: PASS
- `node --check frontend/js/control.js`: PASS
- `python -m pytest integration_tests -q`: PASS — 82 tests

## Runtime check expected
After starting `main_sim_only`, wait about 5–10 seconds, then refresh/poll HMI:
- SIM TEST should become online.
- MATLAB MAIN can remain no_data unless operational `main.py` phases exist.
- FluidNC can remain offline because main_sim_only deliberately does not connect FluidNC.
