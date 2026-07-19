# Mission 04 Ready-to-Run — GRBL/FluidNC-like Planner

## Goal

Hoàn thiện planner theo hướng GRBL/FluidNC-like để chương trình chạy ổn định hơn với G-code thực tế hơn, nhưng không phá Mission 01–03.

## What was added

- Python evidence planner: `tools/grbl_fluidnc_planner.py`.
- Planner self-test: `tools/mission4_planner_selftest.py`.
- MATLAB runtime support in `matlab_bridge/CNC3_Gcode_TCP_ClosedLoop_R2023b.m`:
  - `G54..G59` work coordinate systems.
  - `G10 L2 P1..P6` work offset programming.
  - `G92` coordinate offset.
  - `G2/G3` XY arcs using `I/J` or `R`, linearized into safe segments.
  - soft-limit no-enqueue fail-safe.
- MATLAB validation runner: `matlab_bridge/RUN_MISSION_04_PLANNER_R2023B.m`.
- One-click scripts:
  - `RUN_40_MISSION_04_PLANNER_SELFTEST.bat`
  - `RUN_41_MISSION_04_PLAN_GCODE_FILE.bat`
  - `RUN_42_MISSION_04_MATLAB_PLANNER.bat`
- Documentation:
  - `agentic_execution_kit/12_MISSION_04_GRBL_FLUIDNC_PLANNER.md`
  - `agentic_execution_kit/13_AXIS_1D_MODEL_BLUEPRINT.md`

## How to run

First run the regression gate:

```text
RUN_ME_FIRST_LOCAL_VERIFY.bat
```

Then run Mission 04 planner self-test:

```text
RUN_40_MISSION_04_PLANNER_SELFTEST.bat
```

To validate the patched MATLAB/Simulink planner runtime on MATLAB R2023b:

```text
RUN_42_MISSION_04_MATLAB_PLANNER.bat
```

To plan any custom G-code file:

```text
RUN_41_MISSION_04_PLAN_GCODE_FILE.bat your_file.nc
```

## Expected outputs

```text
reports/mission4_planner/mission4_planner_selftest_summary.md
reports/mission4_planner/*_planned_segments.csv
reports/mission4_planner/*_planner_result.json
reports/mission4_matlab_planner/mission4_matlab_planner_results.csv
reports/mission4_matlab_planner/mission4_matlab_planner_summary.md
```

## Verification summary

Sandbox verification passed:

- `compileall`: PASS.
- `pytest integration_tests -v`: PASS, 45 tests.
- Mission 04 planner self-test: PASS, 6/6 cases.
- Mission 02 benchmark regression: PASS.
- CNC3 virtual lab regression: PASS.
- full-loop mock self-test: PASS.
- `node --check`: PASS.

## Side note — 1D model like the screenshot

The screenshot shows a detailed axis-level 1D plant: step/direction pulses, driver, motor electrical stage, mechanical load/screw/table, and axis output. That is the correct high-fidelity direction, but it should be integrated incrementally. Mission 04 focuses on planner correctness and safe G-code interpretation; the detailed 1D driver–motor axis should be introduced as a separate validated subsystem later so it does not break the full-loop MATLAB/NX path that already works.

## Limitations

This implementation is GRBL/FluidNC-like, not a byte-for-byte copy of FluidNC `planner.cpp`. The Python planner includes conservative look-ahead/junction speed annotation for evidence and reporting. The MATLAB runtime keeps the motion loop stable and adds WCS/G92/arcs/soft-limit support, but exact FluidNC junction dynamics still require future calibration.
