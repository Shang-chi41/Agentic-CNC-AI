# Unified Runtime Contract

## Endpoint

```text
GET /api/system/status
```

## Response shape

```json
{
  "timestamp": "...",
  "runtime": {
    "active_entrypoint": "main | main_sim_only | multiple | none",
    "live_entrypoints": ["main"],
    "stale_after_s": 15,
    "main": {"fresh": true, "age_s": 2.1, "env": {}},
    "main_sim_only": {"fresh": false, "age_s": null, "env": {}}
  },
  "connection": {
    "fluidnc": {"connected": true, "status": "online", "source": "main.fluidnc_telnet_socket"},
    "matlab_main": {"connected": true, "status": "online", "source": "main.matlab_sender_socket"},
    "sim_test": {"connected": false, "status": "no_data", "source": "main_sim_only.runtime_heartbeat"},
    "nxmcd": {"connected": true, "status": "online", "source": "nxmcd_tcp_client"},
    "mongodb": {"connected": true, "status": "online", "source": "cloud_mongo_ping"}
  },
  "dataflow": {
    "mode": "pre_run_check | machine_run | manual_jog_or_direct_line | connectivity_test | idle",
    "source_of_truth": "matlab_simulink | fluidnc_mpos | main_sim_only | none",
    "drives_nx_mcd": true
  },
  "gate": {
    "machine_run_allowed": false,
    "gate_enabled": true,
    "run_gcode_target": "machine",
    "reason": "Per-G-code gate is evaluated by Cloud/Edge run_gcode command"
  }
}
```

## Rule summary
- CONNECTION is service-level truth, not simulation-data truth.
- RUNTIME is entrypoint-level truth.
- DATAFLOW is owner/source-of-truth truth.
- GATE is machine-run permission truth.
- `main_sim_only` can only prove SIM TEST, never MATLAB MAIN and never machine-run readiness.
