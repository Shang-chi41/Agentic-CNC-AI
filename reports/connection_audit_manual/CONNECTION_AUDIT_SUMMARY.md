# Full System Connection Audit

Generated: 2026-07-14T03:44:10.878047+00:00

```text
Mode: safe-live
Profile: all
Overall: PASS
Required failures: 0
Critical/blocker findings: 0
```

## Results

| ID | Component | Level | Status | Severity | Summary |
|---|---|---|---|---|---|
| S001 | project_inventory | static | PASS | NOTE | Required architecture files present |
| S002 | env_contract | static | PASS | NOTE | `.env` and `.env.example` key parity |
| S003 | required_env | static | PASS | NOTE | Required connection configuration is present |
| S004 | runtime_profiles | static | PASS | NOTE | Machine and simulation launch profiles remain separated |
| S005 | direct_env_profile | static | PASS | NOTE | Direct environment does not combine machine target with disabled gate |
| S006 | unified_status_consumer | static | PASS | NOTE | Frontend renders the unified system status contract |
| S007 | system_status_source_contract | static | PASS | NOTE | Cloud status separates connection/runtime/dataflow/gate |
| S008 | runtime_snapshot_contract | static | PASS | NOTE | main and main_sim_only report separate connection truth |
| S009 | port_contract | static | PASS | NOTE | Core TCP ports are distinct and match the MATLAB/NX contract |
| S010 | bridge_env_contract | static | PASS | NOTE | MATLAB bridge reads the same four port variables |
| S011 | stdio_tool_server | sandbox | PASS | NOTE | MCP stdio tools/list returns exactly 8 tools |
| S012 | provider_configuration | static | PASS | NOTE | Configured AI provider has its required connection setting |
| S013 | edge_cloud_sync | static | PASS | NOTE | Edge→Cloud sync authentication and runtime heartbeat paths align |
| S014 | pose_relay_contract | static | PASS | NOTE | Pose HTTP publish and authenticated WebSocket relay are wired |
| S015 | docker_contract | static | WARN | MAJOR | Docker comments describe Atlas/Aura while current `.env` points to local services |
| L001 | cloud_health | safe-live | PASS | NOTE | Cloud health endpoint reachable |
| L002 | mongodb | safe-live | PASS | NOTE | MongoDB ping |
| L003 | neo4j | safe-live | PASS | NOTE | Neo4j connectivity and read query |
| P8000 | cloud_8000 | safe-live | PASS | NOTE | TCP listener detected on port 8000 |
| P5000 | matlab_edge_in_5000 | safe-live | UNKNOWN | MAJOR | TCP listener not detected on port 5000 |
| P5001 | edge_matlab_recv_5001 | safe-live | PASS | NOTE | TCP listener detected on port 5001 |
| P5100 | simulink_gcode_5100 | safe-live | UNKNOWN | MAJOR | TCP listener not detected on port 5100 |
| P5101 | simulink_frame_5101 | safe-live | UNKNOWN | MAJOR | TCP listener not detected on port 5101 |
| P6001 | edge_nxmcd_6001 | safe-live | PASS | NOTE | TCP listener detected on port 6001 |
| L004 | unified_system_status | safe-live | SKIP | NOTE | JWT not provided; device connection truth cannot be read from Cloud |

## Verification levels

```text
static     = source/config/contract only
sandbox    = local isolated process/test
safe-live  = safe runtime/database/passive-port checks
full-live  = explicitly allowed active network/provider probes
```

## Safety

- This audit never sends G-code.
- This audit never connects as a fake NX MCD client.
- LLM calls are disabled unless `--allow-ai-call` is supplied.
- Reports contain no API keys, passwords or tokens.

## Manual next step

Run while the intended runtime is active:

```bat
RUN_99_FULL_CONNECTION_AUDIT.bat safe-live all
```

For actual FluidNC/MQTT/LLM/Telegram probes:

```bat
RUN_99_FULL_CONNECTION_AUDIT.bat full-live all ai
```
