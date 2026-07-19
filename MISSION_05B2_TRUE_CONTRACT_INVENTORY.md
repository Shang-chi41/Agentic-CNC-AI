# Inventory — Mission 05B.2

## Runtime entrypoints
- `edge_backend/main.py`: operational runtime, starts SensorWorker, SimulationWorker, MatlabSender, NXMCDClient, TelnetCollector, SyncWorker, CommandWorker, AIWorker and runtime heartbeat.
- `edge_backend/main_sim_only.py`: test/simulation runtime, starts SimulationWorker, MatlabSender, GcodeSimDispatchWorker, NXMCDClient, SyncWorker, AIWorker and runtime heartbeat. It deliberately does not start FluidNC/TelnetCollector/CommandWorker/SensorWorker.

## Cloud APIs
- `GET /api/system/status`: unified contract for runtime/connection/dataflow/gate.
- `POST /api/sync/runtime_status`: Edge runtime heartbeat upsert into `Runtime_Status`.
- `POST /api/control/run/{gcode_id}`: now branches simulation vs machine target.

## Source-of-truth mapping
| UI dot | Source |
|---|---|
| FluidNC | `main.py` runtime status → `fluidnc.connection_status()` |
| MATLAB MAIN | `MatlabSender.status().connected` or recent `MatlabReceiver.status().connected` |
| SIM TEST | fresh `main_sim_only` runtime heartbeat |
| NX MCD | `nxmcd_client.status().connected` |
| MongoDB | Cloud `mongo_ping()` |

## Gate mapping
- Simulation/test: allowed without machine gate; queues `simulation_status=queued`.
- Machine run: requires `_gcode_machine_run_ready` and sends `Machine_Commands.run_gcode` only after authorization.
