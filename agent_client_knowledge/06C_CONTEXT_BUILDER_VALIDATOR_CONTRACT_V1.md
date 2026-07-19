# 06C — CONTEXT BUILDER + VALIDATOR CONTRACT V1

> Mission 06C chốt contract cho `get_neo4j_context` / context builder và `validate_gcode`.
>
> Scope: artifact độc lập, không sửa code project hiện tại.

---

## P0 — Freeze input

Dựa trên freeze của 06A/06B và contract Neo4j hiện có.

---

## P1 — Goal Understanding

Mục tiêu 06C:

```text
Nhận Intent từ 06B
→ build context từ Neo4j
→ cung cấp OperatingRange làm source-of-truth cho F/S/depth
→ định nghĩa validator để chặn G-code sai trước khi trả final.
```

---

## P2 — Inventory dữ liệu cần lưu

```text
1. Context builder input/output.
2. Matching rule Tool + Operation + Material + OperatingRange.
3. Cypher contract.
4. Validator input/output.
5. Severity policy.
6. Data quality checks.
7. Sample contexts OR1–OR4.
```

---

## P3 — Evaluation Matrix cho 06C

| ID | Scenario | Expected | Must not happen | Evidence |
|---|---|---|---|---|
| Ctx1 | Intent khớp OR1 | context_status=ready, range_id=OR1 | chọn range khác | context JSON |
| Ctx2 | Intent khớp OR2 | context_status=ready, range_id=OR2 | dùng F/S tự đoán | context JSON |
| Ctx3 | Drilling chưa có graph | unsupported/needs_clarification | tự map thành milling | context_status |
| Val1 | G-code F/S trong range | passed=true | báo lỗi sai | validation report |
| Val2 | G-code F vượt range | BLOCKER | vẫn cho final | validation report |
| Val3 | G-code S vượt Tool.max_rpm | ERROR/BLOCKER | bỏ qua max_rpm | validation report |
| Val4 | X/Y/Z vượt travel | BLOCKER | bỏ qua axis limit | validation report |

---

## P4 — Source-of-Truth Contract

| Data | Source-of-truth |
|---|---|
| OperatingRange | Neo4j Tool + Operation + Material shared range |
| F | `operating_range.feed_min/feed_max` |
| S | `operating_range.spindle_min/spindle_max` and Tool.max_rpm |
| depth | `operating_range.depth_min/depth_max` |
| axis limits | Neo4j Axis |
| final validity | `validate_gcode` report |
| machine-run permission | Existing CHECK/Confirm gate, not validator alone |

---

## P5 — Guardrails

```text
[ ] Context Builder không tự bịa OperatingRange.
[ ] Validator fail nếu thiếu context.
[ ] F/S/depth ngoài range là BLOCKER.
[ ] Operation chưa có graph thì unsupported/needs_clarification.
[ ] G-code valid không đồng nghĩa được chạy máy thật.
```

---

## P6 — Contract chi tiết

### Context Builder

```json
{
  "function_name": "build_gcode_context",
  "input": "Intent object from 06B",
  "output": {
    "context_status": "ready | needs_clarification | unsupported | no_matching_range",
    "machine": "Machine object",
    "axis_limits": "Axis map",
    "selected_tool": "Tool object",
    "selected_operation": "Operation object",
    "selected_material": "Material object",
    "operating_range": "OperatingRange object",
    "selection_reason": "why this tool/op/material/range was selected",
    "fallback_used": "boolean",
    "warnings": "list",
    "source": {
      "range_id": "OR1/OR2/OR3/OR4",
      "tool_id": "T1/T2/T3",
      "op_id": "OP1/OP2/OP3",
      "material": "material name"
    }
  },
  "matching_rule": [
    "Prefer exact Tool + Operation + Material match.",
    "If tool missing, choose tool only if one unambiguous OperatingRange matches operation/material.",
    "If operation/material unsupported, return unsupported or needs_clarification, not guessed range.",
    "If multiple ranges match, return needs_clarification unless a deterministic project rule exists."
  ],
  "cypher_contract": [
    "Match Tool, Operation, Material sharing the same OperatingRange.",
    "Return machine and axes with the selected range.",
    "Ensure spindle_max <= Tool.max_rpm.",
    "Ensure material.hardness <= Machine.max_hardness_HB."
  ]
}
```

### Validator

```json
{
  "function_name": "validate_gcode",
  "input": [
    "gcode",
    "context"
  ],
  "output": {
    "passed": "boolean",
    "severity": "PASS | WARNING | ERROR | BLOCKER",
    "issues": [
      {
        "code": "string",
        "severity": "WARNING | ERROR | BLOCKER",
        "message": "string",
        "line": "int|null",
        "actual": "any",
        "allowed": "any",
        "suggested_fix": "string|null"
      }
    ],
    "parsed": {
      "feed_values": [],
      "spindle_values": [],
      "xyz_extents": {},
      "max_stepdown_mm": null,
      "has_required_header": "boolean"
    },
    "suggested_gcode_patch": "string|null"
  },
  "checks": [
    "F within feed_min/feed_max.",
    "S within spindle_min/spindle_max.",
    "S <= selected_tool.max_rpm.",
    "Z depth/stepdown within depth_min/depth_max.",
    "X/Y/Z extents within axis travel.",
    "Material hardness <= Machine max hardness.",
    "Header contains G21/G90/G17 or configured equivalent.",
    "No real machine execution command; Agent only generates/checks."
  ],
  "severity_policy": {
    "BLOCKER": [
      "Missing Neo4j context.",
      "F/S/depth outside OperatingRange.",
      "Axis travel exceeded.",
      "Machine-run attempt without gate."
    ],
    "ERROR": [
      "Missing safe header.",
      "Tool max RPM exceeded.",
      "Unsupported operation/material/tool mapping."
    ],
    "WARNING": [
      "Feed/spindle near range boundary.",
      "Optional metadata missing.",
      "User requested unsupported style but safe fallback exists."
    ]
  }
}
```

### Data Quality Checks

```json
[
  "Each OperatingRange has exactly one Tool, one Operation, and one Material.",
  "feed_min <= feed_max.",
  "spindle_min <= spindle_max.",
  "depth_min <= depth_max.",
  "spindle_max <= Tool.max_rpm.",
  "Material.hardness <= Machine.max_hardness_HB.",
  "Axis travel is present for X/Y/Z.",
  "No orphan OperatingRange.",
  "No ambiguous range for supported intent."
]
```

### Sample Contexts

```json
{
  "OR1": {
    "intent_example": "Beginner asks to rough mill aluminum 6061.",
    "context": {
      "context_status": "ready",
      "selected_tool": {
        "type": "Dao phay ngón 2 me (Flat End Mill)",
        "diameter_mm": 6,
        "material": "Carbide (WC-Co)",
        "max_rpm": 24000
      },
      "selected_operation": {
        "type": "milling",
        "name": "Phay thô (Roughing)"
      },
      "selected_material": {
        "name": "Nhôm 6061",
        "hardness_HB": 95,
        "recommended_feed_ratio": 1.6
      },
      "operating_range": {
        "tool_id": "T1",
        "operation_id": "OP1",
        "material": "Nhôm 6061",
        "current_min_A": 1.0,
        "current_rms_A": 1.6,
        "current_max_A": 2.3,
        "feed_min_mm_min": 600,
        "feed_max_mm_min": 1500,
        "spindle_min_rpm": 14000,
        "spindle_max_rpm": 20000,
        "depth_min_mm": 1.0,
        "depth_max_mm": 3.0
      },
      "source": {
        "range_id": "OR1",
        "tool_id": "T1",
        "op_id": "OP1",
        "material": "Nhôm 6061"
      }
    }
  },
  "OR2": {
    "intent_example": "Roughing normalized C45 steel.",
    "context": {
      "context_status": "ready",
      "selected_tool": {
        "type": "Dao phay ngón 4 me (Flat End Mill)",
        "diameter_mm": 10,
        "material": "Carbide (WC-Co)",
        "max_rpm": 18000
      },
      "selected_operation": {
        "type": "milling",
        "name": "Phay thô (Roughing)"
      },
      "selected_material": {
        "name": "Thép C45 (thường hóa)",
        "hardness_HB": 200,
        "recommended_feed_ratio": 1.0
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
  },
  "OR3": {
    "intent_example": "Finish milling hardened 40Cr steel.",
    "context": {
      "context_status": "ready",
      "selected_tool": {
        "type": "Dao phay ngón 2 me (Flat End Mill)",
        "diameter_mm": 6,
        "material": "Carbide (WC-Co)",
        "max_rpm": 24000
      },
      "selected_operation": {
        "type": "milling",
        "name": "Phay tinh (Finishing)"
      },
      "selected_material": {
        "name": "Thép 40Cr (đã tôi)",
        "hardness_HB": 350,
        "recommended_feed_ratio": 0.65
      },
      "operating_range": {
        "tool_id": "T1",
        "operation_id": "OP2",
        "material": "Thép 40Cr (đã tôi)",
        "current_min_A": 1.2,
        "current_rms_A": 1.9,
        "current_max_A": 2.6,
        "feed_min_mm_min": 100,
        "feed_max_mm_min": 350,
        "spindle_min_rpm": 4000,
        "spindle_max_rpm": 7000,
        "depth_min_mm": 0.1,
        "depth_max_mm": 0.5
      },
      "source": {
        "range_id": "OR3",
        "tool_id": "T1",
        "op_id": "OP2",
        "material": "Thép 40Cr (đã tôi)"
      }
    }
  },
  "OR4": {
    "intent_example": "Slot milling hardened SKD11.",
    "context": {
      "context_status": "ready",
      "selected_tool": {
        "type": "Dao phay ngón mini 2 me",
        "diameter_mm": 3,
        "material": "Carbide (WC-Co)",
        "max_rpm": 24000
      },
      "selected_operation": {
        "type": "milling",
        "name": "Phay rãnh (Slot milling)"
      },
      "selected_material": {
        "name": "Thép SKD11 (tôi cứng)",
        "hardness_HB": 550,
        "recommended_feed_ratio": 0.35
      },
      "operating_range": {
        "tool_id": "T3",
        "operation_id": "OP3",
        "material": "Thép SKD11 (tôi cứng)",
        "current_min_A": 2.0,
        "current_rms_A": 2.9,
        "current_max_A": 3.61,
        "feed_min_mm_min": 40,
        "feed_max_mm_min": 150,
        "spindle_min_rpm": 2500,
        "spindle_max_rpm": 5000,
        "depth_min_mm": 0.05,
        "depth_max_mm": 0.3
      },
      "source": {
        "range_id": "OR4",
        "tool_id": "T3",
        "op_id": "OP3",
        "material": "Thép SKD11 (tôi cứng)"
      }
    }
  }
}
```

---

## P7 — Ultra-review

| Reviewer | Result |
|---|---|
| Architect | PASS — 06C nối đúng 06B intent → Neo4j context → validator |
| Neo4j/Data | PASS — có matching rule và sample OR1–OR4 |
| Safety | PASS — F/S/depth ngoài range là BLOCKER |
| Critic | MAJOR NOTE — drilling/pocket/engraving chưa có graph, phải unsupported hoặc hỏi lại |

---

## P8 — Handoff

Next: **06D — Eval Harness C1/C2/C3/C4**.

06D dùng contract 06B/06C để tính số liệu thay vì đánh giá cảm tính.
