# Mission 04B — Integrated 3-Axis Detailed 1D Driver–Motor Plant V2

## Goal

Redo Mission 04B with the Full Agentic Work Skill and add two extra sandbox verification layers:

```text
GNU Octave
→ MATLAB-like numerical check for portable `.m` logic

PathSim-compatible reference
→ Python block-diagram / ODE reference for the per-axis 1D plant
```

The target architecture is now:

```text
Mission 04 GRBL/FluidNC-like planner
→ command X/Y/Z position
→ Axis_X/Y/Z detailed 1D plant
→ step/dir conversion
→ pulse expander
→ direction-to-voltage diagnostic
→ stepper driver current/torque approximation
→ leadscrew + mass/friction 1D load
→ sensor position/velocity/acceleration
→ CNC3 116-byte frame sender
→ Edge bridge
→ NX MCD 96-byte frame
```

## What changed in V2

Added sandbox verification layers:

```text
tools/pathsim_axis1d_reference.py
tools/octave_axis1d_selftest.m
RUN_63_MISSION_04B_PATHSIM_REFERENCE.bat
RUN_64_MISSION_04B_OCTAVE_SELFTEST.bat
integration_tests/test_mission04b_pathsim_octave_reference.py
agentic_execution_kit/16_MISSION_04B_PATHSIM_OCTAVE_VALIDATION.md
```

Updated:

```text
RUN_62_MISSION_04B_FULL_REGRESSION.bat
agentic_execution_kit/15_MISSION_04B_AXIS1D_INTEGRATED_RUNBOOK.md
PROJECT_MEMORY_MISSION04B_UPDATE.md
```

## How to run

Run the one-click regression first:

```text
RUN_62_MISSION_04B_FULL_REGRESSION.bat
```

This now runs:

```text
compileall
pytest
Mission 04 planner self-test
Axis1D reference self-test
PathSim-compatible Axis1D reference
optional GNU Octave numerical self-test
```

Then create/update the Simulink model in MATLAB R2023b:

```text
RUN_60_MISSION_04B_CREATE_AXIS1D_INTEGRATED_MODEL.bat
```

Then compile-check it in MATLAB:

```text
RUN_61_MISSION_04B_MATLAB_SELFTEST.bat
```

Optional direct checks:

```text
RUN_63_MISSION_04B_PATHSIM_REFERENCE.bat
RUN_64_MISSION_04B_OCTAVE_SELFTEST.bat
```

`RUN_64` will not fail if GNU Octave is not installed; it prints a clear skip message and exits cleanly.

## Generated model

```text
models/chay_dao_3axis_axis1d_integrated_R2023b.slx
```

## Expected subsystem structure

Each axis subsystem is separated as:

| Block | Role |
|---|---|
| `01_PositionCommand_to_StepDir` | Planner command position to step/dir |
| `02_Pulse_Expander` | Visible pulse expansion |
| `03_Direction_to_Voltage` | Direction sign/voltage diagnostic |
| `04_Stepper_Driver_Current_Torque` | Phase-current and torque approximation |
| `05_Leadscrew_Mass_Friction_Load` | Leadscrew, table mass, damping/friction load |
| `PositionMM / VelocityMMs / AccelerationMMs2 / TorqueNm` | Sensor/report outputs |

## Verification in sandbox

| Check | Result |
|---|---|
| `python -m compileall edge_backend cloud_backend tools virtual_lab integration_tests` | PASS |
| `python -m pytest integration_tests -q` | PASS, 63 tests |
| `python tools/mission4_planner_selftest.py` | PASS |
| `python tools/axis1d_driver_motor_model.py` | PASS |
| `python tools/pathsim_axis1d_reference.py` | PASS |
| `python virtual_lab/cnc3_virtual_lab.py` | PASS |
| `python tools/full_loop_mock_selftest.py` | PASS |
| `node --check frontend/js/*.js` | PASS |

## PathSim / Octave scope

```text
PathSim-compatible reference PASS
→ proves the Axis1D block-equation plant is numerically stable in sandbox.

Octave self-test
→ optional MATLAB-like numerical check if GNU Octave is installed.

Neither replaces MATLAB/Simulink/Simscape/NX MCD real verification.
```

## Important safety decision

The verified Mission 01–04 production model remains unchanged:

```text
models/chay_dao_3axis_nx_loop_R2023b.slx
```

Mission 04B V2 creates and verifies a separate integrated detailed 1D plant path so the full-loop fallback is protected.
