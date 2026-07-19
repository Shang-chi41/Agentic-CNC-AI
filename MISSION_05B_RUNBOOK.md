# Mission 05B Runbook

## 1. Machine/main runtime
Copy machine profile values into `.env`, then run:

```powershell
RUN_70_MAIN_MACHINE.bat
```

Expected HMI:
- `MATLAB MAIN` online only after MATLAB bridge accepts Edge connection.
- `FluidNC` online only after FluidNC Telnet socket is connected.
- `NX MCD` online only after NX MCD TCP client connects to Edge.
- G-code machine run remains blocked unless CHECK PASS → approved → Confirm → confirmed.

## 2. Sim-only connectivity runtime
Copy sim_only profile values into `.env`, then run:

```powershell
RUN_71_MAIN_SIM_ONLY.bat
```

Expected HMI:
- `SIM TEST` online within `RUNTIME_HEARTBEAT_S` and Cloud sync latency.
- `MATLAB MAIN` does not become online only because `main_sim_only` is alive.
- `FluidNC` stays offline/disabled because sim_only does not start FluidNC.
- `NX MCD` becomes online only after NX MCD client connects to Edge.

## 3. Direct API check
After login, call:

```text
GET /api/system/status
```

Use this endpoint as the single frontend/operator status truth.
