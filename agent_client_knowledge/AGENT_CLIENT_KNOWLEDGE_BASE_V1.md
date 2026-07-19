# AGENT CLIENT KNOWLEDGE BASE V1

> Mission: **06A — Knowledge Base + Contract Foundation**
>
> Mục tiêu: tạo một file lưu trữ riêng cho bước đầu xây dựng **AI Agentic Client sinh G-code theo ngữ cảnh**, không thay đổi cấu trúc tổng thể của project hiện tại.
>
> Vai trò file này: **bộ nhớ / contract / nguồn cập nhật độc lập** cho Neo4j Knowledge Graph, prompt đa trình độ, tool order, evaluation và guardrail.

---

## 0. Trạng thái

```yaml
version: "1.0"
status: "DRAFT_BASELINE"
mission: "06A"
scope: "standalone knowledge artifacts only"
affects_project_structure: false
created_at_utc: "2026-07-10T16:04:39.800946+00:00"
```

Mission này **không sửa**:

```text
frontend/
cloud_backend/
edge_backend/
main.py
main_sim_only.py
.env
RUN*.bat
tool_runner.py
provider_manager.py
```

Mission này chỉ tạo:

```text
AGENT_CLIENT_KNOWLEDGE_BASE_V1.md
AGENT_CLIENT_CONTRACT_V1.json
```

---

## 1. P0 — Freeze input hiện có

| Input | Exists | Size | SHA256 |
|---|---:|---:|---|
| `FULL_AGENTIC_WORK_SKILL_V3_VI(1).md` | True | 34772 | `812a4c26eaad8fa690533f139f285f960482d909932ccaafa972c95d1dfd68ee` |
| `SPEC_mcp_agent_gcode_v1.md` | True | 8610 | `c277bd294607a1fc3174bd2e2ab1885fd74b4cd3fbffd22007b93a5d75a9fe70` |
| `cnc_knowledge_graph_seed.cypher` | True | 12319 | `a9cdc45110cb4e97b5ed033590f582da2f2af5f85e21dec79e92ee3705ac413c` |
| `image(91).png` | True | 802431 | `6d48158eee496f8d34bce72b503dcdae17469233340bcf5e2b8d08e6d4d98515` |

Các input này được dùng làm baseline cho Mission 06A.

---

## 2. P1 — Goal Understanding

### Goal

Tạo một **file memory/contract độc lập** để lưu dữ liệu nền cho Agent Client sinh G-code theo ngữ cảnh.

Agent Client sau này phải:

```text
1. Hiểu yêu cầu tự nhiên hoặc ảnh phôi.
2. Nhận diện trình độ người dùng.
3. Hỏi lại nếu thiếu thông tin nguy hiểm.
4. Gọi get_neo4j_context trước khi sinh G-code.
5. Dùng F/S/depth từ Neo4j operating_range.
6. Sinh G-code.
7. Gọi validate_gcode.
8. Tự sửa nếu vi phạm.
9. Trả kết quả phù hợp trình độ người vận hành.
```

### Non-goals

```text
Không code MCP server ở mission này.
Không sửa tool_runner.py.
Không sửa provider_manager.py.
Không sửa project runtime.
Không thay đổi .env/RUN scripts.
Không chạy máy thật.
Không claim real runtime verified.
```

### Definition of Done

```text
[ ] Có file Markdown memory/contract cho người dùng cập nhật.
[ ] Có file JSON contract cho agent/code đọc sau này.
[ ] Có Neo4j schema inventory.
[ ] Có OperatingRange rõ.
[ ] Có User-Level Adapter.
[ ] Có Tool Contract.
[ ] Có Evaluation Matrix C1/C2/C3/C4.
[ ] Có Source-of-Truth Contract.
[ ] Có Guardrails.
[ ] Có Handoff cho mission kế tiếp.
```

---

## 3. P2 — Inventory dữ liệu cần lưu

File này lưu các nhóm dữ liệu sau:

```text
1. Kiến trúc tổng thể Agent Client.
2. Neo4j Knowledge Graph schema.
3. Machine/Axis/Tool/Operation/Material/OperatingRange.
4. Prompt đa trình độ: beginner / intermediate / expert / unknown.
5. Tool contract: get_neo4j_context, generate_gcode, validate_gcode.
6. Evaluation Matrix C1/C2/C3/C4.
7. Source-of-Truth Contract.
8. Guardrails.
9. Update protocol.
10. Roadmap 06A → 06F.
```

---

## 4. Kiến trúc tổng thể Agent Client

```text
User natural language / image
→ User-Level Adapter
→ Intent Clarifier
→ get_neo4j_context
→ Neo4j Context Contract
→ G-code generation
→ validate_gcode
→ self-correction loop
→ final G-code + explanation by user level
→ simulation/check
→ operator approval
→ machine-run gate
```

### Nguyên tắc quan trọng

```text
Neo4j context phải ổn trước MCP.
Validator phải ổn trước sinh G-code final.
Prompt đa trình độ phải có trước khi mở cho người dùng thật.
MCP chỉ là transport/tool boundary, không phải nguồn trí tuệ chính.
```

---

## 5. Neo4j Knowledge Graph Schema

### Labels

| Label | Properties |
|---|---|
| Machine | `name`, `axes_count`, `work_volume_mm`, `spindle_power_kW`, `max_workpiece_mm`, `max_workpiece_kg`, `max_hardness_HB`, `note` |
| Axis | `name`, `travel_mm`, `max_feed`, `home_offset` |
| Tool | `tool_id`, `type`, `diameter_mm`, `material`, `max_rpm` |
| Operation | `op_id`, `type`, `name` |
| Material | `name`, `hardness`, `recommended_feed_ratio` |
| OperatingRange | `range_id`, `current_min_A`, `current_rms_A`, `current_max_A`, `feed_min`, `feed_max`, `spindle_min`, `spindle_max`, `depth_min`, `depth_max` |
| AlarmPattern | `label`, `symptoms` |
| MaintenanceRule | `rule_id`, `trigger`, `action`, `severity` |

### Relationships

```text
(:Machine)-[:HAS_AXIS]->(:Axis)
(:Machine)-[:HAS_TOOL]->(:Tool)
(:Machine)-[:PERFORMS]->(:Operation)
(:Tool)-[:USED_FOR]->(:Operation)
(:Operation)-[:APPLIED_ON]->(:Material)
(:Tool)-[:HAS_RANGE]->(:OperatingRange)
(:Operation)-[:HAS_RANGE]->(:OperatingRange)
(:Material)-[:HAS_RANGE]->(:OperatingRange)
(:OperatingRange)-[:MAY_TRIGGER]->(:AlarmPattern)
(:AlarmPattern)-[:RECOMMENDS]->(:MaintenanceRule)
(:OperatingRange)-[:RECOMMENDS]->(:MaintenanceRule)
```

---

## 6. Machine / Axis / Tool / Operation / Material

### Machine

| Field | Value |
|---|---|
| name | CNC_VerticalMill_Mini_01 |
| axes_count | 3 |
| work_volume_mm | 400x300x100 |
| spindle_power_kW | 1.5 |
| max_workpiece_mm | 100x100x60 |
| max_workpiece_kg | 20 |
| max_hardness_HB | 550 |

### Axis limits

| Axis | travel_mm | max_feed_mm_min | home_offset_mm |
|---|---:|---:|---:|
| X | 400 | 3000 | -5 |
| Y | 300 | 3000 | -5 |
| Z | 100 | 1500 | -2 |

### Tools

| Tool | Type | Diameter | Material | Max RPM |
|---|---|---:|---|---:|
| T1 | Dao phay ngón 2 me (Flat End Mill) | 6 mm | Carbide (WC-Co) | 24000 |
| T2 | Dao phay ngón 4 me (Flat End Mill) | 10 mm | Carbide (WC-Co) | 18000 |
| T3 | Dao phay ngón mini 2 me | 3 mm | Carbide (WC-Co) | 24000 |

### Operations

| ID | Name | Type |
|---|---|---|
| OP1 | Phay thô (Roughing) | milling |
| OP2 | Phay tinh (Finishing) | milling |
| OP3 | Phay rãnh (Slot milling) | milling |

### Materials

| Material | Hardness HB | Feed ratio |
|---|---:|---:|
| Nhôm 6061 | 95 | 1.6 |
| Thép C45 (thường hóa) | 200 | 1.0 |
| Thép 40Cr (đã tôi) | 350 | 0.65 |
| Thép SKD11 (tôi cứng) | 550 | 0.35 |

---

## 7. OperatingRange — Source-of-truth cho F/S/depth

| Range | Tool | Operation | Material | Feed mm/min | Spindle rpm | Depth mm | Current A |
|---|---|---|---|---:|---:|---:|---:|
| OR1 | T1 | OP1 | Nhôm 6061 | 600–1500 | 14000–20000 | 1.0–3.0 | rms 1.6 / max 2.3 |
| OR2 | T2 | OP1 | Thép C45 (thường hóa) | 250–700 | 6000–10000 | 0.5–1.5 | rms 2.36 / max 3.0 |
| OR3 | T1 | OP2 | Thép 40Cr (đã tôi) | 100–350 | 4000–7000 | 0.1–0.5 | rms 1.9 / max 2.6 |
| OR4 | T3 | OP3 | Thép SKD11 (tôi cứng) | 40–150 | 2500–5000 | 0.05–0.3 | rms 2.9 / max 3.61 |

### Rule

```text
Agent không được tự bịa F/S/depth từ kiến thức nội tại.
F/S/depth final phải nằm trong OperatingRange lấy từ Neo4j.
```

---

## 8. User-Level Adapter — Prompt phù hợp người nhiều trình độ

### Level: Beginner

```text
Dành cho người mới, không rành G-code/CNC.

Agent phải:
- Hỏi từng thông tin ngắn.
- Giải thích đơn giản.
- Không đưa quá nhiều G-code thô trước khi xác nhận.
- Dùng safe defaults nếu hợp lệ và nói rõ.
- Nếu thiếu material/depth/origin thì hỏi lại.
```

### Level: Intermediate

```text
Dành cho người biết CNC cơ bản.

Agent phải:
- Cho biết dao, vật liệu, operation, F/S/Z đã chọn.
- Giải thích ngắn vì sao chọn.
- Cho phép chỉnh tham số nhưng chỉ trong operating_range.
- Trả validation report sau khi sinh G-code.
```

### Level: Expert

```text
Dành cho người biết G-code/CAM.

Agent phải:
- Trả G-code trực tiếp.
- Kèm Neo4j context và validation report.
- Giải thích tối thiểu.
- Không hỏi lại nếu đủ material, operation, geometry, depth, origin.
```

### Level: Unknown

```text
Mặc định an toàn.

Agent phải:
- Dùng phong cách beginner/intermediate.
- Hỏi lại khi thiếu thông tin nguy hiểm.
- Không tự suy luận tham số cắt.
```

### User-Level Prompt Core

```text
Bạn là CNC G-code Agent cho Smart Desktop CNC.

Bạn phải hỗ trợ người dùng ở nhiều trình độ:
- Beginner: hướng dẫn từng bước, giải thích đơn giản.
- Intermediate: giải thích ngắn, cho phép chỉnh tham số trong ngưỡng.
- Expert: trả G-code, Neo4j context và validation report trực tiếp.

Luôn làm theo thứ tự:
1. Hiểu yêu cầu gia công.
2. Xác định trình độ người dùng.
3. Xác định vật liệu, dao, nguyên công, kích thước, độ sâu, gốc tọa độ.
4. Nếu thiếu thông tin nguy hiểm, hỏi lại.
5. Gọi get_neo4j_context trước khi sinh G-code.
6. Chỉ dùng feed/spindle/depth từ operating_range Neo4j.
7. Sinh G-code.
8. Gọi validate_gcode.
9. Nếu sai, tự sửa trong giới hạn tool rounds.
10. Trả kết quả phù hợp trình độ người dùng.
```

---

## 9. Tool Contract

### get_neo4j_context

```yaml
must_call_before_final_gcode: true
source_of_truth: Neo4j Knowledge Graph
input:
  - user_request
  - user_level
  - material?
  - operation?
  - tool?
  - geometry?
  - depth?
output_required:
  - machine
  - axis_limits
  - selected_tool
  - selected_operation
  - selected_material
  - operating_range
  - source
```

Output chuẩn đề xuất:

```json
{
  "machine": {
    "name": "CNC_VerticalMill_Mini_01",
    "axes_count": 3,
    "work_volume_mm": "400x300x100",
    "spindle_power_kW": 1.5,
    "max_workpiece_mm": "100x100x60",
    "max_workpiece_kg": 20,
    "max_hardness_HB": 550,
    "note": "Phay đứng CNC cỡ nhỏ; dao chủ yếu là dao phay ngón"
  },
  "axis_limits": {
    "X": {
      "travel_mm": 400,
      "max_feed_mm_min": 3000,
      "home_offset_mm": -5
    },
    "Y": {
      "travel_mm": 300,
      "max_feed_mm_min": 3000,
      "home_offset_mm": -5
    },
    "Z": {
      "travel_mm": 100,
      "max_feed_mm_min": 1500,
      "home_offset_mm": -2
    }
  },
  "selected_tool": {
    "tool_id": "T2",
    "type": "Dao phay ngón 4 me (Flat End Mill)",
    "diameter_mm": 10
  },
  "selected_operation": {
    "op_id": "OP1",
    "name": "Phay thô (Roughing)"
  },
  "selected_material": {
    "name": "Thép C45 (thường hóa)",
    "hardness_HB": 200
  },
  "operating_range": {
    "tool_id": "T2",
    "operation_id": "OP1",
    "material": "Thép C45 (thường hóa)",
    "current_min_A": 1.4,
    "current_rms_A": 2.36,
    "current_max_A": 3.0,
    "feed_min_mm_min": 250,
    "feed_max_mm_min": 700,
    "spindle_min_rpm": 6000,
    "spindle_max_rpm": 10000,
    "depth_min_mm": 0.5,
    "depth_max_mm": 1.5
  },
  "source": {
    "range_id": "OR2",
    "tool_id": "T2",
    "op_id": "OP1",
    "material": "Thép C45 (thường hóa)"
  }
}
```

### generate_gcode

```yaml
allowed_after:
  - get_neo4j_context
must_use:
  - operating_range
  - axis_limits
  - user_level_adapter
not_allowed:
  - internal LLM F/S/depth guess
```

### validate_gcode

```yaml
must_call_before_final_response: true
checks:
  - F within operating_range.feed_min/feed_max
  - S within operating_range.spindle_min/spindle_max
  - Z stepdown/depth within operating_range.depth_min/depth_max
  - X/Y/Z within Axis travel
  - safe header exists, e.g. G21/G90/G17 or project-standard equivalent
  - no machine run unless later CHECK/gate approves
```

---

## 10. P3 — Evaluation Matrix

| ID | Tiêu chí | Cách đo | Ngưỡng đạt |
|---|---|---|---:|
| C1 | Tool ordering đúng | Log tool_calls: `get_neo4j_context` xuất hiện trước G-code final | 100% |
| C2 | G-code trong ngưỡng ngay lần sinh đầu | Parse F/S so với `operating_range` Neo4j | ≥ 90% |
| C3 | Tự sửa khi vi phạm | Nếu C2 fail vòng 1, agent gọi validate/sửa trong ≤ 2 vòng | ≥ 95% |
| C4.1 | Nhận diện trình độ | So response style với beginner/intermediate/expert/unknown | ≥ 90% |
| C4.2 | Beginner không bị quá tải | Không trả quá nhiều thuật ngữ/G-code thô trước khi xác nhận | ≥ 90% |
| C4.3 | Expert không bị dài dòng | Expert nhận G-code/context/validation trực tiếp | ≥ 90% |
| C4.4 | Thiếu thông tin nguy hiểm thì hỏi lại | Nếu thiếu material/depth/origin thì không tự bịa | 100% |
| C4.5 | Safety không đổi theo trình độ | Mọi level vẫn phải dùng Neo4j + validate_gcode | 100% |

---

## 11. P4 — Source-of-Truth Contract

| State/Data | Source-of-truth | Không được dùng |
|---|---|---|
| Feed F | Neo4j `OperatingRange.feed_min/feed_max` | LLM memory / kinh nghiệm chung |
| Spindle S | Neo4j `OperatingRange.spindle_min/spindle_max` | LLM memory / thông số web không kiểm chứng |
| Depth | Neo4j `OperatingRange.depth_min/depth_max` | đoán theo vật liệu |
| Axis limits | Neo4j `Axis.travel_mm`, `Axis.max_feed` | UI hoặc prompt người dùng nếu vượt máy |
| Tool max rpm | Neo4j `Tool.max_rpm` | OperatingRange nếu vượt Tool.max_rpm |
| User response style | User-Level Adapter | một prompt chung cho mọi người |
| G-code validity | `validate_gcode` với Neo4j context | cảm giác “có vẻ đúng” |
| Machine run permission | CHECK/Confirm machine gate hiện có | Agent Client tự quyết chạy máy |
| MCP | Transport gọi tool | Không thay đổi logic tool |

---

## 12. P5 — Guardrails

```text
[ ] Không output final G-code nếu chưa gọi get_neo4j_context.
[ ] Không dùng F/S/depth từ kiến thức nội tại của LLM.
[ ] Không vượt operating_range.
[ ] Không bỏ validate_gcode.
[ ] Không chạy máy thật trực tiếp từ Agent Client.
[ ] Không dùng cùng prompt style cho mọi trình độ.
[ ] Không cập nhật Neo4j schema mà quên Evaluation Matrix.
[ ] Không build MCP trước khi context/validator contract ổn.
[ ] Không claim real runtime verified nếu chưa chạy trên máy thật.
[ ] Không ảnh hưởng cấu trúc tổng thể project trong Mission 06A.
```

---

## 13. Data Quality Checks cho Neo4j

Các check cần chạy khi có eval harness hoặc Neo4j test script:

```text
[ ] Mỗi OperatingRange có đúng 1 Tool.
[ ] Mỗi OperatingRange có đúng 1 Operation.
[ ] Mỗi OperatingRange có đúng 1 Material.
[ ] feed_min <= feed_max.
[ ] spindle_min <= spindle_max.
[ ] depth_min <= depth_max.
[ ] spindle_max <= Tool.max_rpm.
[ ] material.hardness <= Machine.max_hardness_HB.
[ ] Axis travel đủ cho geometry yêu cầu.
[ ] Không có OperatingRange mồ côi.
[ ] Không có material/tool/operation không query được.
```

---

## 14. Update Protocol — Khi người dùng muốn cập nhật

### Cập nhật thủ công

```text
1. Mở AGENT_CLIENT_KNOWLEDGE_BASE_V1.md.
2. Sửa section liên quan: Tool / Material / OperatingRange / Prompt / Guardrail.
3. Mở AGENT_CLIENT_CONTRACT_V1.json.
4. Sửa dữ liệu máy đọc tương ứng.
5. Nếu thêm Tool/Material/Operation mới, thêm ít nhất 1 scenario vào Evaluation Matrix.
6. Nếu đổi prompt đa trình độ, cập nhật C4.
7. Nếu đổi OperatingRange, cập nhật validate_gcode contract.
8. Chạy eval C1/C2/C3/C4 khi eval harness đã có.
```

### Rule cập nhật

```text
Không cập nhật dữ liệu mà không cập nhật tiêu chí kiểm chứng.
Không thêm tool/material/operation mà không thêm test case.
Không đổi source-of-truth nếu chưa ghi lý do.
```

---

## 15. Mission Roadmap

```text
06A — Knowledge Base + Contract Foundation
06B — Neo4j Context Builder + Query Contract
06C — User-Level Prompt + Intent Clarifier
06D — Validator Contract + Eval Harness C1/C2/C3/C4
06E — MCP Tool Server wrapper
06F — Agent Client integration
```

---

## 16. P7 — Ultra-review

### Architect Review

```text
PASS — Mission 06A chỉ tạo knowledge artifacts, không ảnh hưởng project runtime.
PASS — Kiến trúc đúng thứ tự: Neo4j context trước Agent/MCP.
```

### Neo4j/Data Review

```text
PASS — Đã inventory labels, relationships, machine, axes, tools, operations, materials, operating ranges.
MAJOR NOTE — Graph hiện tại mới đủ cho chế độ cắt cơ bản, chưa đủ cho full CAM strategy như pocket/contour/drilling/engraving.
```

### Prompt/User-Level Review

```text
PASS — Đã thêm beginner/intermediate/expert/unknown.
PASS — Safety contract không đổi theo trình độ.
```

### Safety/G-code Review

```text
PASS — Đã cấm final G-code nếu chưa có Neo4j context và validate_gcode.
PASS — Machine run vẫn thuộc CHECK/Confirm gate, không thuộc Agent Client.
```

### Evaluation Review

```text
PASS — Đã có C1/C2/C3 từ spec MCP và C4 cho đa trình độ.
NOTE — Chưa chạy eval thật vì mission này chưa tạo eval harness.
```

### Guardrail Review

```text
PASS — Đã có guardrail chống bịa F/S, vượt operating_range, bỏ validate, chạy máy thật.
```

---

## 17. P8 — Handoff

### Deliverables

```text
AGENT_CLIENT_KNOWLEDGE_BASE_V1.md
AGENT_CLIENT_CONTRACT_V1.json
```

### Next recommended mission

```text
Mission 06B — Neo4j Context Builder + Query Contract
```

### 06B nên làm

```text
1. Viết query contract cho get_neo4j_context.
2. Viết Cypher query lấy Tool + Operation + Material + OperatingRange.
3. Viết fallback khi không match đầy đủ.
4. Viết data quality checker cho Neo4j.
5. Tạo unit test cho OR1–OR4.
```

### Open questions

```text
1. Người dùng muốn mặc định user_level là beginner hay unknown?
2. Gốc tọa độ mặc định của G-code là góc phôi, tâm phôi hay machine zero?
3. Có cho Agent tự chọn tool khi người dùng không chỉ định không?
4. Có cần sinh toolpath pocket/contour/drilling ở giai đoạn 06B hay chỉ chuẩn bị context?
5. Có cần thêm operation drilling/engraving/pocket milling vào Neo4j trước eval 20 case không?
```

---

## 18. Tóm tắt một dòng

```text
Agent Client sinh G-code đúng = User-Level Prompt + Neo4j Context + OperatingRange + validate_gcode + Evaluation C1/C2/C3/C4 + Guardrails.
```
