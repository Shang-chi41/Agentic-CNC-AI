# Mission 04+ — Bản hoàn chỉnh thêm blueprint mô hình 1D driver–motor từng trục

## Mục tiêu

Kế thừa Mission 01–04 đã chạy thành công và bổ sung đường tích hợp mô hình 1D driver–motor chi tiết theo từng trục, nhưng không phá runtime cũ.

## Trạng thái

| Hạng mục | Trạng thái |
|---|---|
| Mission 01 full-loop MATLAB/NX MCD | Giữ nguyên |
| Mission 02 benchmark + collision safety | Giữ nguyên |
| Mission 03 subsystem/report model | Giữ nguyên |
| Mission 04 GRBL/FluidNC-like planner | Giữ nguyên |
| Axis 1D driver–motor blueprint | Đã bổ sung |
| Python reference self-test | Đã bổ sung |
| MATLAB System object cho 1 trục | Đã bổ sung |
| Script tạo model Simulink Axis 1D report/detail | Đã bổ sung |

## Chạy nhanh

```text
RUN_ME_FIRST_LOCAL_VERIFY.bat
RUN_50_MISSION_04_AXIS1D_BLUEPRINT_SELFTEST.bat
RUN_51_MISSION_04_CREATE_AXIS1D_MODEL.bat
```

## File quan trọng

```text
tools/axis1d_driver_motor_model.py
matlab_bridge/Axis1DDriverMotorDetailed_R2023B.m
matlab_bridge/RUN_MISSION_04_AXIS1D_UNIT_SELFTEST_R2023B.m
matlab_bridge/create_axis1d_driver_motor_detail_model_R2023b.m
matlab_bridge/RUN_MISSION_04_CREATE_AXIS1D_DETAIL_MODEL_R2023B.m
agentic_execution_kit/13_AXIS_1D_MODEL_BLUEPRINT.md
agentic_execution_kit/14_AXIS_1D_INTEGRATION_RUNBOOK.md
integration_tests/test_axis1d_driver_motor_model.py
integration_tests/test_axis1d_matlab_static.py
```

## Nguyên tắc an toàn

Bản này chưa thay production full-loop bằng detailed Axis 1D model. Detailed model chạy riêng để kiểm chứng và chụp hình báo cáo. Khi muốn đưa vào production, dùng shadow mode trước.
