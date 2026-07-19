# SPEC — Mission 05B.2 True Runtime/System Contract

## Problem
Previous fixes mixed service connection, runtime mode, dataflow, and machine-run gate. This caused repeated incorrect UI behavior, including status dots lighting from shared heartbeat/log data rather than their own service/device connection truth.

## Expected behavior
1. `main_sim_only` is a test/simulation runtime. It is not blocked by machine G-code safety gate.
2. `main.py` is the operational runtime. Real machine G-code execution remains gated.
3. SYSTEM CONNECTION dots reflect only service/device connection:
   - FluidNC: real FluidNC socket/Telnet connection.
   - MATLAB MAIN: MATLAB bridge socket/recent MATLAB packet, not check result.
   - SIM TEST: main_sim_only runtime heartbeat.
   - NX MCD: real NX MCD TCP client connection.
   - MongoDB: Cloud MongoDB ping.
4. Frontend must not recompute connection or gate from unrelated fields.
5. Simulation run path must allow unapproved G-code to be sent to simulation queue without opening the real machine gate.

## Non-goals
- Do not validate real hardware in sandbox.
- Do not remove existing machine safety gate for FluidNC machine runs.
- Do not use Simulation_Data as service connection truth.

## Acceptance criteria
- [x] Connection source-of-truth uses Runtime_Status/service status, not Simulation_Data.
- [x] MATLAB connection is not old packet_count forever.
- [x] NX MCD connection depends on TCP client connection.
- [x] FluidNC connection depends on FluidNC Telnet object state.
- [x] main_sim_only allows simulation queue without machine gate.
- [x] machine target still uses `_gcode_machine_run_ready`.
- [x] frontend run buttons allow simulation runtime without confirmed status.
- [x] tests/checks pass in sandbox.
