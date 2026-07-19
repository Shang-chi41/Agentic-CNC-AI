# AGENTIC RUN FIRST — bắt buộc đọc trước khi sửa

## Quy trình sửa mission mới

Trước khi sửa code, đọc:

```text
agentic_execution_kit/17_SELF_GOVERNING_WORKFLOW_LOCK.md
agentic_execution_kit/18_AGENTIC_GCODE_GEOMETRY_CONTRACT.md
```

## Luật bắt buộc

```text
[ ] Không sửa khi chưa freeze baseline.
[ ] Không sửa khi chưa biết source-of-truth.
[ ] Không sửa khi chưa viết expected/forbidden behavior.
[ ] Không sửa khi chưa có regression test cho lỗi người dùng gặp.
[ ] Không claim full runtime nếu chỉ chạy sandbox/targeted tests.
```

## Quick command

```bat
RUN_ME_FIRST_LOCAL_VERIFY.bat
```

Log nằm trong `reports/`.

## Local verify gồm

- compileall
- pytest integration_tests
- virtual lab
- bridge pacing lab
- full loop mock selftest
- planner selftest
- frontend JS check bằng `tools/check_frontend_js.py`

## Khi sửa Agentic G-code

Không được nhầm:

```text
user geometry ≠ machine travel
OperatingRange depth_max ≠ final total depth
validator failure ≠ root-cause explanation
```


## Mission 06G3 thêm rule bắt buộc

Đọc thêm:

```text
agentic_execution_kit/19_AGENTIC_CURRENT_PROMPT_PRIORITY_CONTRACT.md
```

Luật mới:

```text
current user question > context/chat history > machine metadata
```

Không được để `400x300x100` trong context/machine metadata ghi đè kích thước túi `20x10` của câu người dùng hiện tại.

## Mission 07 — Full System Connection Audit

Trước khi kết luận hệ thống đã kết nối đầy đủ, chạy:

```bat
RUN_99_FULL_CONNECTION_AUDIT.bat static all
RUN_99_FULL_CONNECTION_AUDIT.bat safe-live all
```

Đọc:

```text
agentic_execution_kit/MISSION_07_FULL_CONNECTION_AUDIT/
reports/full_connection_audit/CONNECTION_AUDIT_SUMMARY.md
```

Không được claim MATLAB/NX/FluidNC/LLM live từ static audit.


## Mission 08 — Agentic Flexibility Core

Trước khi kết luận Agent Client trả lời linh hoạt, đọc:

```text
agentic_execution_kit/MISSION_08_AGENTIC_FLEXIBILITY_CORE/
```

Chạy evaluation bắt buộc:

```bat
RUN_92_AGENTIC_FLEXIBILITY_EVAL.bat
```

Luật khóa:

```text
actual AIWorker entrypoint phải gọi Agentic Response Harness
current turn > attachment > recent user turns > machine metadata
Neo4j → generation → validate_gcode → repair tối đa 2 vòng
generation/static validation/MATLAB/NX/approval là các tầng riêng
optimization không được đổi geometry invariants
không claim live LLM/hardware từ mock/sandbox evaluation
```


## Mission 09 — CHECK completion, gate/dataflow, arc preview, verified pattern learning

Đọc trước khi sửa/check:

```text
agentic_execution_kit/MISSION_09_CHECK_GATE_ARC_KNOWLEDGE/
```

Chạy:

```bat
RUN_94_MISSION09_CHECK_GATE_ARC_KNOWLEDGE_EVAL.bat
```

Luật khóa:

```text
dispatch_progress=100% không đồng nghĩa motion_complete
CHECK pass chỉ từ exact check_id + CNC3 motion_complete + terminal status
CONNECT TEST / CHECK / HOME SYNC / MACHINE RUN là trạng thái khác nhau
sim_only không được làm sáng MACHINE RUN
G2/G3 preview phải nội suy cung và giữ tọa độ WCS âm
verified G-code chỉ được dùng để học sau static PASS + motion complete + no collision + operator Confirm
pattern dạy chiến lược; Neo4j vẫn sở hữu F/S/stepdown
```
