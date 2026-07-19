# Mission 02 Ready-to-Run Status

## Đã bổ sung

- Bộ G-code benchmark 6 case.
- Tool Python dependency-free `tools/mission2_position_benchmark.py`.
- MATLAB script `matlab_bridge/RUN_MISSION_02_BENCHMARK_R2023B.m`.
- Script chạy nhanh `.bat` và `.ps1`.
- Test regression `integration_tests/test_mission2_position_benchmark.py`.
- Local verify đã chạy thêm Mission 02 virtual benchmark.

## Cách chạy nhanh

1. `RUN_ME_FIRST_LOCAL_VERIFY.bat`
2. `RUN_20_MISSION_02_VIRTUAL_BENCHMARK.bat`
3. `RUN_21_MISSION_02_MATLAB_BENCHMARK.bat`

## Output chính

- `reports/mission2_benchmark/mission2_benchmark_summary.md`
- `reports/mission2_benchmark/mission2_benchmark_results.csv`
- `reports/mission2_benchmark/mission2_benchmark_frames.csv`
- `reports/mission2_benchmark/mission2_endpoint_error_chart.svg`
- `reports/mission2_matlab_benchmark/mission2_matlab_benchmark_summary.md`
- `reports/mission2_matlab_benchmark/mission2_matlab_benchmark_results.csv`
- `reports/mission2_matlab_benchmark/mission2_matlab_benchmark_frames.csv`

## Lưu ý

Sandbox chỉ xác nhận Python/virtual benchmark và code packaging. MATLAB/NX thật vẫn cần chạy trên máy của bạn.


---

## NX MCD Collision Safety Patch

This package now includes a collision stop/reset loop:

```text
NX MCD collision feedback
→ Edge latches collision
→ MATLAB CHECK frames are dropped
→ MATLAB bridge receives abort/reset
→ Simulink G-code input receives __RESET__
→ NX setpoints return to home pose
→ frontend.pose publishes COLLISION_STOPPED
```

Run this mock test without real NX MCD:

```text
RUN_23_MOCK_NX_COLLISION_TEST.bat
```

See:

```text
agentic_execution_kit/11_NX_MCD_COLLISION_SAFETY.md
```
