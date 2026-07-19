# Session Handoff — Mission 05B

## Completed
Unified runtime/system status contract implemented.

## Main source of truth
Frontend should use:

```text
GET /api/system/status
```

## Runtime rules
- `main.py` = runtime chính for CHECK/RUN/JOG/direct line.
- `main_sim_only.py` = connectivity test only.
- CONNECTION does not equal RUN permission.
- Machine run remains gated by CHECK PASS + Confirm.

## Next local validation
1. Start Cloud backend.
2. Start `RUN_71_MAIN_SIM_ONLY.bat`; confirm SIM TEST online only.
3. Stop sim_only.
4. Start `RUN_70_MAIN_MACHINE.bat`; confirm MATLAB MAIN/FluidNC/NX MCD reflect real connections.
5. Try running unconfirmed G-code; confirm blocked.
6. CHECK PASS + Confirm + Run; confirm allowed.
