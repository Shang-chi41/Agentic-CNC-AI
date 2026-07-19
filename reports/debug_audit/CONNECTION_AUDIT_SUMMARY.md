# Full System Connection Audit

Generated: 2026-07-14T17:13:58.319005+00:00

```text
Mode: static
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
| S015 | docker_contract | static | PASS | NOTE | Docker compose basic contract is aligned |
| S016 | three_primary_flow_ownership | static | PASS | NOTE | CHECK, RUN and JOG ownership paths remain present |

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

To read the canonical unified status without storing a JWT in a file, set
temporary process credentials before the audit:

```powershell
$env:CONNECTION_AUDIT_USERNAME = "<operator>"
$env:CONNECTION_AUDIT_PASSWORD = "<password>"
RUN_99_FULL_CONNECTION_AUDIT.bat safe-live all
Remove-Item Env:CONNECTION_AUDIT_USERNAME, Env:CONNECTION_AUDIT_PASSWORD
```

For actual FluidNC/MQTT/LLM/Telegram probes:

```bat
RUN_99_FULL_CONNECTION_AUDIT.bat full-live all ai
```
