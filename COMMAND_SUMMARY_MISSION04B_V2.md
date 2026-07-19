# Command Summary — Mission 04B V2

| Command | Result |
|---|---|
| `python -m compileall edge_backend cloud_backend tools virtual_lab integration_tests` | PASS |
| `python -m pytest integration_tests -q` | PASS — 63 tests |
| `python tools/mission4_planner_selftest.py --out reports/mission4_planner` | PASS |
| `python tools/axis1d_driver_motor_model.py --out reports/mission4_axis1d` | PASS |
| `python tools/pathsim_axis1d_reference.py --out reports/mission4b_pathsim` | PASS |
| `python virtual_lab/cnc3_virtual_lab.py` | PASS |
| `python tools/full_loop_mock_selftest.py` | PASS |
| `node --check frontend/js/*.js` | PASS |

## Not run in sandbox

| Command | Reason |
|---|---|
| `RUN_60_MISSION_04B_CREATE_AXIS1D_INTEGRATED_MODEL.bat` | Requires MATLAB R2023b |
| `RUN_61_MISSION_04B_MATLAB_SELFTEST.bat` | Requires MATLAB R2023b |
| NX MCD real connection | Requires user workstation / NX MCD |
| GNU Octave runtime command | GNU Octave is optional and not installed in this sandbox |
