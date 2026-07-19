# Mission 01–06 Ready Status

## Đã thực hiện trong gói này

- Thêm bộ script chạy nhanh ở project root.
- Thêm `agentic_execution_kit/` gồm runbook, G-code test, template evidence, task board.
- Vá `tools/full_loop_mock_selftest.py` để chạy được trong sandbox sạch bằng fake simulation repository, không bắt buộc MongoDB cho test mock.
- Vá `edge_backend/utils/__init__.py` sang lazy import để import logger/tool nhẹ không kéo dependency database khi chưa cần.
- Bổ sung `RUN_GCODE_TARGET`, `ALLOW_SIMULATION_RUN`, `RUN_PERMISSION_GATE` vào `.env.example`.
- Chạy lại sandbox verification.

## Kết quả verification trong sandbox

| Lệnh | Kết quả |
|---|---|
| `compileall` | PASS |
| `pytest integration_tests -q` | PASS, 21 passed |
| `node --check frontend/js/*.js` | PASS |
| `virtual_lab/cnc3_virtual_lab.py` | PASS, 372 frames, max X/Y/Z = 30/10/5 mm |
| `bridge_pacing_lab.py` | PASS, speedup 14.85x |
| `tools/full_loop_mock_selftest.py` | PASS, Edge sender → fake MATLAB → Edge receiver → ControlSelector → NX 12 LREAL |

## Vẫn cần bạn chạy trên máy thật

- MATLAB/Simulink Editor Running.
- NX MCD thật nhận 96 byte và drive chạy.
- FluidNC/máy CNC thật chỉ chạy sau khi safety gate pass.
