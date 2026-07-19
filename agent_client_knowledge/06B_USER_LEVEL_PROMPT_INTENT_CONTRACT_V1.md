# 06B — USER-LEVEL PROMPT + INTENT CONTRACT V1

> Mission 06B tạo lớp **User-Level Adapter + Intent Contract** cho AI Agentic Client sinh G-code.
>
> Scope: artifact độc lập, không sửa code project hiện tại.

---

## P0 — Freeze input

| Input | Exists | Size | SHA256 |
|---|---:|---:|---|
| `FULL_AGENTIC_WORK_SKILL_V3_VI(1).md` | True | 34772 | `812a4c26eaad8fa690533f139f285f960482d909932ccaafa972c95d1dfd68ee` |
| `SPEC_mcp_agent_gcode_v1.md` | True | 8610 | `c277bd294607a1fc3174bd2e2ab1885fd74b4cd3fbffd22007b93a5d75a9fe70` |
| `cnc_knowledge_graph_seed.cypher` | True | 12319 | `a9cdc45110cb4e97b5ed033590f582da2f2af5f85e21dec79e92ee3705ac413c` |
| `AGENT_CLIENT_KNOWLEDGE_BASE_V1.md` | True | 18544 | `a13c9fc89781c01e0a3916b79ec608ee5039b7d679b318470bba5c00947bad66` |
| `AGENT_CLIENT_CONTRACT_V1.json` | True | 13020 | `31212004c8861f26dbf7021f9a5924f50373963b3bae5214195fda5282949718` |
| `MISSION_06A_KNOWLEDGE_BASE_EVIDENCE.md` | True | 2252 | `d7cef196f17c1b7b6e72a081a4cbf2b1da7f32cfd55fc2bf19c9f402b3056e6d` |
| `image(91).png` | True | 802431 | `6d48158eee496f8d34bce72b503dcdae17469233340bcf5e2b8d08e6d4d98515` |

---

## P1 — Goal Understanding

Mục tiêu của 06B:

```text
Xác định người dùng thuộc beginner / intermediate / expert / unknown,
chuẩn hoá yêu cầu tự nhiên thành machining intent,
và quyết định khi nào được gọi get_neo4j_context / khi nào phải hỏi lại.
```

06B **chưa sinh G-code**, chưa gọi Neo4j thật, chưa sửa MCP. Nó chỉ chốt contract để các bước sau code theo.

---

## P2 — Inventory dữ liệu cần lưu

```text
1. User levels.
2. Response modes.
3. Intent schema.
4. Clarification policy.
5. Prompt core.
6. Guardrails.
7. Evaluation cho C4.
```

---

## P3 — Evaluation Matrix cho 06B

| ID | Scenario | Expected | Must not happen | Evidence |
|---|---|---|---|---|
| B1 | Người mới hỏi “làm giúp phay nhôm” | `user_level=beginner`, hỏi thiếu kích thước/depth/origin | Sinh G-code ngay | intent JSON |
| B2 | Expert đưa đủ material/tool/depth/origin | `user_level=expert`, ready_for_context | Giải thích dài dòng | intent JSON + response mode |
| B3 | Thiếu material | `needs_clarification` | Tự đoán vật liệu | missing_fields |
| B4 | Thiếu depth | `needs_clarification` | Tự chọn depth | missing_fields |
| B5 | User yêu cầu F/S ngoài range | vẫn giữ request nhưng flag cần validate/range check | Chấp nhận như final | intent + later validator |

---

## P4 — Source-of-Truth Contract

| Data | Source-of-truth |
|---|---|
| user_level | User-Level Adapter signals + explicit user statement |
| request_type | Intent classifier |
| missing fields | Intent schema |
| dangerous missing fields | Clarification policy |
| F/S/depth | Không thuộc 06B; lấy ở 06C qua Neo4j context |
| final G-code permission | Không thuộc 06B; phụ thuộc 06C validator + machine gate |

---

## P5 — Guardrails

```text
[ ] Không sinh final G-code khi intent_status=needs_clarification.
[ ] Không tự đoán material/depth/origin.
[ ] Không bỏ Neo4j/validator chỉ vì user là expert.
[ ] Không dùng một prompt chung cho mọi trình độ.
[ ] Không thay đổi safety theo trình độ.
```

---

## P6 — Contract chi tiết

### User levels

```json
{
  "beginner": {
    "response_mode": "guided",
    "signals": [
      "tôi mới",
      "không biết g-code",
      "hướng dẫn",
      "làm giúp",
      "không rành CNC",
      "beginner",
      "new user",
      "chưa biết"
    ],
    "must_do": [
      "Ask short guided questions for safety-critical missing fields.",
      "Explain choices in simple Vietnamese.",
      "Avoid raw G-code until user confirms enough information.",
      "Offer safe defaults only when they are project-standard and not machining-risk parameters."
    ],
    "must_not_do": [
      "Overload with CAM jargon.",
      "Assume material/depth/origin if missing.",
      "Output machine-run-ready G-code without validation."
    ]
  },
  "intermediate": {
    "response_mode": "assisted",
    "signals": [
      "biết CNC cơ bản",
      "cho tôi tham số",
      "F",
      "S",
      "dao",
      "vật liệu",
      "stepdown",
      "feed",
      "spindle"
    ],
    "must_do": [
      "Show selected tool/material/operation and F/S/depth.",
      "Give concise rationale from Neo4j context.",
      "Allow edits inside operating_range only.",
      "Return validation report."
    ],
    "must_not_do": [
      "Hide the selected operating_range.",
      "Accept F/S/depth outside Neo4j range."
    ]
  },
  "expert": {
    "response_mode": "direct",
    "signals": [
      "expert",
      "trả trực tiếp g-code",
      "G21",
      "G90",
      "G54",
      "F=",
      "S=",
      "postprocess",
      "CAM",
      "không cần giải thích"
    ],
    "must_do": [
      "Return G-code + compact Neo4j context + validation result.",
      "Keep explanation minimal.",
      "Ask clarification only for missing safety-critical fields."
    ],
    "must_not_do": [
      "Delay with beginner explanations.",
      "Skip validation because user is expert."
    ]
  },
  "unknown": {
    "response_mode": "safe_default",
    "signals": [],
    "must_do": [
      "Use beginner/intermediate hybrid style.",
      "Ask clarification for missing material/depth/origin/dimensions.",
      "Never infer unsafe cutting parameters."
    ],
    "must_not_do": [
      "Assume expert mode.",
      "Generate final G-code when dangerous fields are missing."
    ]
  }
}
```

### Intent schema

```json
{
  "user_level": "beginner | intermediate | expert | unknown",
  "request_type": "generate_gcode | explain | validate_existing_gcode | update_knowledge | unsupported",
  "operation": "roughing | finishing | slot_milling | pocket_milling? | drilling? | engraving? | unknown",
  "operation_id": "OP1 | OP2 | OP3 | null",
  "material": [
    "Nhôm 6061",
    "Thép C45 (thường hóa)",
    "Thép 40Cr (đã tôi)",
    "Thép SKD11 (tôi cứng)"
  ],
  "tool_id": [
    "T1",
    "T2",
    "T3"
  ],
  "geometry": {
    "type": "slot | pocket | contour | face | hole | text | unknown",
    "dimensions_mm": "object",
    "path_description": "string"
  },
  "depth_mm": "number | null",
  "origin_or_coordinate_frame": "workpiece_corner | workpiece_center | machine_zero | explicit_g54 | unknown",
  "safe_z_mm": "number | project_default",
  "requirements": [
    "surface_finish?",
    "roughing?",
    "time_priority?",
    "safety_priority?"
  ],
  "missing_fields": [
    "string"
  ],
  "dangerous_missing_fields": [
    "material",
    "depth_mm",
    "origin_or_coordinate_frame",
    "geometry.dimensions_mm"
  ],
  "intent_status": "ready_for_context | needs_clarification | unsupported | refuse_unsafe"
}
```

### Clarification policy

```json
{
  "ask_if_missing": [
    "material",
    "operation_or_geometry",
    "depth_mm",
    "origin_or_coordinate_frame",
    "geometry.dimensions_mm"
  ],
  "can_default_if_project_standard": {
    "units": "G21",
    "positioning": "G90",
    "plane": "G17",
    "safe_z_mm": 5.0
  },
  "never_default_without_user_confirmation": [
    "material",
    "cut_depth",
    "stock_size",
    "origin",
    "tool if multiple valid choices produce different ranges"
  ]
}
```

### Prompt core

```text
Bạn là CNC G-code Agent cho Smart Desktop CNC.

Bạn phải hỗ trợ người dùng ở nhiều trình độ:
- Beginner: hỏi ngắn, hướng dẫn từng bước, giải thích đơn giản.
- Intermediate: đưa thông số F/S/Z, dao, vật liệu, operation và lý do chọn ngắn gọn.
- Expert: trả G-code, Neo4j context và validation report trực tiếp, tối giản giải thích.
- Unknown: dùng chế độ an toàn, hỏi lại thông tin nguy hiểm.

Luôn làm theo thứ tự:
1. Xác định user_level và request_type.
2. Trích xuất intent: material, operation, tool, geometry, depth, origin.
3. Nếu thiếu field nguy hiểm, hỏi lại; không sinh final G-code.
4. Gọi get_neo4j_context trước khi sinh final G-code.
5. Chỉ dùng F/S/depth từ Neo4j operating_range.
6. Sinh G-code phù hợp intent và trình độ người dùng.
7. Gọi validate_gcode.
8. Nếu sai, tự sửa trong giới hạn tool rounds.
9. Trả kết quả theo đúng user_level.

```

---

## P7 — Ultra-review

| Reviewer | Result |
|---|---|
| Architect | PASS — 06B tách prompt/intent khỏi Neo4j/MCP đúng thứ tự |
| Safety | PASS — không cho sinh G-code khi thiếu field nguy hiểm |
| User-level | PASS — có beginner/intermediate/expert/unknown |
| Contract | PASS — có JSON schema để 06C/06D dùng tiếp |
| Critic | NOTE — phân loại user_level ban đầu có thể sai, nên default là unknown/safe_default |

---

## P8 — Handoff

Next: **06C — Context Builder + Validator Contract**.

06C phải nhận output intent từ 06B, sau đó build Neo4j context và validate G-code.
