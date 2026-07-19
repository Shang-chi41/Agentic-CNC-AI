# Mission 03 — Ready-to-Run Summary

## Goal
Tách Simulink thành subsystem rõ ràng để đưa vào báo cáo, nhưng vẫn giữ mục tiêu chạy không lỗi và không phá các kết quả Mission 01–02.

## Design decision
Mission 03 không sửa phá model runtime cũ. Bản cũ `chay_dao_3axis_nx_loop_R2023b.slx` vẫn là fallback. Mission 03 thêm một model riêng:

```text
models/chay_dao_3axis_report_subsystem_R2023b.slx
```

Model này được tạo bằng script:

```text
matlab_bridge/create_chay_dao_3axis_report_subsystem_model_R2023b.m
```

Nó giữ nguyên core đã chạy được:

```text
CNC3_Gcode_TCP_ClosedLoop_R2023b
```

và bọc vào các subsystem dễ chụp hình/giải thích trong báo cáo.

## Subsystem layout

| Subsystem | Vai trò |
|---|---|
| `01_Gcode_TCP_and_GRBL_Core` | Core đọc G-code 80 byte, parse, planner/step simulation, xuất CNC3 frame |
| `02_Motion_Monitor_Dashboard` | Hiển thị X/Y/Z position, velocity, acceleration |
| `03_Workspace_Logging_and_Benchmark` | Ghi timeseries để benchmark/báo cáo |
| `04_Status_and_Safety_Monitor` | Hiển thị connected, line_seq, send_seq, queue, done, debug bytes |
| `05_NX_MCD_Interface_Contract` | Ghi chú contract NX MCD 96 byte + feedback collision 100 byte |

## One-click files

```text
RUN_31_MISSION_03_LOCAL_VERIFY.bat
RUN_30_MISSION_03_CREATE_SUBSYSTEM_MODEL.bat
RUN_32_MISSION_03_COLLECT_CONTEXT_MEMORY.bat
```

Recommended order:

```text
1. RUN_31_MISSION_03_LOCAL_VERIFY.bat
2. RUN_30_MISSION_03_CREATE_SUBSYSTEM_MODEL.bat
3. RUN_32_MISSION_03_COLLECT_CONTEXT_MEMORY.bat
```

## Verification result in sandbox

| Check | Result |
|---|---|
| `python -m compileall edge_backend cloud_backend tools virtual_lab integration_tests` | PASS |
| `pytest integration_tests -q` | PASS — 34 tests |
| `python virtual_lab/cnc3_virtual_lab.py` | PASS — 372 CNC3/NX frames |
| `python tools/mission2_position_benchmark.py --out-dir reports/mission2_benchmark` | PASS — 6/6 benchmark cases |
| `python tools/mission3_architecture_manifest.py --check --write-memory` | PASS |
| `node --check frontend/js/*.js` | PASS |

## What is verified

- Mission 03 files exist and are referenced by `.bat` scripts.
- Required subsystem names are present in the MATLAB generator.
- Required 21 core output signals are present.
- The report model uses the verified runtime core, not a rewritten risky implementation.
- The report model has a separate name and does not overwrite the production model.
- Runtime settings include fixed-step, pacing and `StopTime=inf`.
- Mission 02 benchmark and collision-patch regression tests still pass.

## What must be verified on your machine

Sandbox cannot run MATLAB/Simulink/NX MCD. On the real Windows machine with MATLAB R2023b, run:

```text
RUN_30_MISSION_03_CREATE_SUBSYSTEM_MODEL.bat
```

Expected result:

```text
[MISSION_03] Report-ready subsystem model "chay_dao_3axis_report_subsystem_R2023b" created, updated, and started.
```

Then open the generated model and use it for screenshots in the report.
