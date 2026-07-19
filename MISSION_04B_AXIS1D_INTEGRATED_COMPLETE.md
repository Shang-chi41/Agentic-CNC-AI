# Mission 04B — Integrated 3-Axis Detailed 1D Driver–Motor Plant

## Goal

Create the complete report-ready and run-ready architecture the user expected:

```text
Mission 04 GRBL/FluidNC-like planner
→ per-axis command position
→ step/dir conversion
→ pulse expander
→ direction-to-voltage diagnostic
→ stepper driver current/torque approximation
→ leadscrew + mass + damping/friction 1D load
→ position/velocity/acceleration sensor outputs
→ CNC3 116-byte frame
→ Edge bridge
→ NX MCD 96-byte frame
```

The production Mission 01–04 model remains unchanged as fallback. Mission 04B adds a new integrated model script and component System objects.

## Why this fixes the previous blueprint issue

The previous Axis 1D blueprint used one large `Axis1DDriverMotorDetailed_R2023B` block per axis. It worked for a safe first blueprint, but visually it looked too abstract: the user expected the inner chain to be separated like a real 1D physical model.

Mission 04B now separates the axis plant into visible blocks:

| Block | Role |
|---|---|
| `01_PositionCommand_to_StepDir` | converts planner position to one-step-at-a-time step/dir |
| `02_Pulse_Expander` | makes step pulses visible for driver-level logic |
| `03_Direction_to_Voltage` | diagnostic direction voltage/sign block |
| `04_Stepper_Driver_Current_Torque` | pseudo phase-current and torque generation |
| `05_Leadscrew_Mass_Friction_Load` | 1D load with screw pitch, mass, damping/friction and torque-limited acceleration |
| `PositionMM / VelocityMMs / AccelerationMMs2 / TorqueNm` | sensor/report outputs |

## New model to create in MATLAB

Run:

```text
RUN_60_MISSION_04B_CREATE_AXIS1D_INTEGRATED_MODEL.bat
```

This creates:

```text
models/chay_dao_3axis_axis1d_integrated_R2023b.slx
```

Then run compile/update check in MATLAB R2023b:

```text
RUN_61_MISSION_04B_MATLAB_SELFTEST.bat
```

## Regression safety

The verified production model is not replaced:

```text
models/chay_dao_3axis_nx_loop_R2023b.slx
```

Mission 04B is an integration model. If MATLAB layout or detailed plant tuning needs adjustment, the Mission 01–04 full-loop fallback remains available.

## Files added

```text
matlab_bridge/AxisPositionCommandToStepDir_R2023B.m
matlab_bridge/AxisPulseExpander_R2023B.m
matlab_bridge/AxisDirectionToVoltage_R2023B.m
matlab_bridge/AxisStepperDriverCurrentTorque_R2023B.m
matlab_bridge/AxisMechanicalLoad1D_R2023B.m
matlab_bridge/CNC3ResetFromDebugBytes_R2023B.m
matlab_bridge/CNC3Axis1DFrameSender_R2023B.m
matlab_bridge/create_chay_dao_3axis_axis1d_integrated_model_R2023b.m
matlab_bridge/RUN_MISSION_04B_CREATE_AXIS1D_INTEGRATED_MODEL_R2023B.m
matlab_bridge/RUN_MISSION_04B_AXIS1D_INTEGRATED_SELFTEST_R2023B.m
integration_tests/test_mission04b_axis1d_integrated_static.py
RUN_60_MISSION_04B_CREATE_AXIS1D_INTEGRATED_MODEL.bat
RUN_61_MISSION_04B_MATLAB_SELFTEST.bat
RUN_62_MISSION_04B_FULL_REGRESSION.bat
```

## Sandbox verification

| Check | Result |
|---|---|
| `python -m compileall edge_backend cloud_backend tools virtual_lab integration_tests` | PASS |
| `python -m pytest integration_tests -q` | PASS, 60 tests |
| `python tools/mission4_planner_selftest.py` | PASS |
| `python tools/axis1d_driver_motor_model.py` | PASS |
| `python virtual_lab/cnc3_virtual_lab.py` | PASS |
| `python tools/full_loop_mock_selftest.py` | PASS |
| `node --check frontend/js/*.js` | PASS |

## What still requires the user machine

Sandbox cannot run MATLAB R2023b/NX MCD. User must run:

```text
RUN_61_MISSION_04B_MATLAB_SELFTEST.bat
```

and then run the full Edge/MATLAB/NX loop if they want real NX verification.

## Important design decision

Mission 04B uses lightweight MATLAB System blocks instead of full Simscape electrical/mechanical blocks so that the model can be created and compiled more reliably in MATLAB/Simulink R2023b without requiring extra Simscape licenses. The subsystem layout still matches the intended engineering chain and can be upgraded later by replacing `04_Stepper_Driver_Current_Torque` and `05_Leadscrew_Mass_Friction_Load` with Simscape blocks.
