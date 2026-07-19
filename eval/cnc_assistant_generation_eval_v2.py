#!/usr/bin/env python3
"""Service-free end-to-end evaluation for CNC Technical Assistant V2.

Mocks only external Neo4j/MCP transport. The real language parser, context
resolver, deterministic geometry generator, process planner, geometry critic,
static-validation orchestration and response renderer are exercised.
No AI provider, MATLAB, NX, FluidNC or machine command is used.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def context(*, defaults: bool = True, diameter: float = 6.0) -> dict[str, Any]:
    value: dict[str, Any] = {
        "machine": {"name": "CNC", "work_volume_mm": "400x300x100"},
        "axes": [
            {"name": "X", "travel_mm": 400},
            {"name": "Y", "travel_mm": 300},
            {"name": "Z", "travel_mm": 100},
        ],
        "tool": {"name": "T1", "diameter_mm": diameter, "max_rpm": 24000},
        "material": {"name": "Nhôm 6061"},
        "operating_range": {
            "range_id": "OR-T1-AL6061",
            "feed_min": 600,
            "feed_max": 1500,
            "spindle_min": 14000,
            "spindle_max": 20000,
            "depth_min": 1.0,
            "depth_max": 3.0,
        },
    }
    if defaults:
        value["project_defaults"] = {
            "wcs": "G54",
            "origin": "lower_left",
            "safe_z_mm": 10.0,
        }
    return value


SCENARIOS = [
    *[
        {
            "id": f"GEN-OUT-{i:02d}",
            "question": q,
            "contains": [
                "VALIDATED_DRAFT",
                "RECTANGULAR CONTOUR 60x60 MM OUTSIDE",
                "G0 X-3 Y-3",
                "G1 X63 Y63 F1050",
                "G1 Z-3 F600",
                "G1 Z-6 F600",
            ],
            "not_contains": ["APPROVED", "run_permission"],
        }
        for i, q in enumerate(
            [
                "phay contour ngoài 60x60x6",
                "phay biên ngoài 60×60 xuống 6",
                "profile OD 60 60 sâu 6",
                "chạy bao ngoài 60x60x6",
                "phay ngoài chữ nhật 60x60 sâu 6",
                "phay ngoài vuông 60 sâu 6",
                "mill outside profile 60x60x6",
                "cắt chu vi ngoài 60x60 sâu 6",
            ],
            1,
        )
    ],
    {
        "id": "GEN-IN-01",
        "question": "phay contour trong chữ nhật 60x40x3",
        "contains": ["VALIDATED_DRAFT", "RECTANGULAR CONTOUR 60x40 MM INSIDE", "G0 X3 Y3", "G1 X57 Y37"],
    },
    {
        "id": "GEN-CIRCLE-01",
        "question": "phay contour ngoài tròn phi 40 sâu 2",
        "contains": ["VALIDATED_DRAFT", "CIRCULAR CONTOUR R20 MM OUTSIDE", "X43 Y20", "I-23"],
    },
    {
        "id": "GEN-POCKET-01",
        "question": "phay túi chữ nhật 20x10x5",
        "contains": ["VALIDATED_DRAFT", "RECTANGULAR POCKET 20x10 MM", "G0 X3 Y3", "Z-3", "Z-5"],
    },
    {
        "id": "GEN-POCKET-CIRCLE-01",
        "question": "phay túi tròn bán kính 15 sâu 5",
        "contains": ["VALIDATED_DRAFT", "CIRCULAR POCKET R15 MM", "CIRCLE CENTER: X15 Y15"],
    },
    {
        "id": "GEN-SLOT-01",
        "question": "phay rãnh 50x10x3",
        "contains": ["VALIDATED_DRAFT", "SLOT 50x10 MM"],
    },
    {
        "id": "GEN-FACE-01",
        "question": "phay mặt 80x50x0.5",
        "contains": ["VALIDATED_DRAFT", "RECTANGULAR FACE 80x50 MM"],
    },
    {
        "id": "GEN-INCH-01",
        "question": "mill outside contour 2x2x0.25 inch",
        "contains": ["VALIDATED_DRAFT", "RECTANGULAR CONTOUR 50.8x50.8 MM OUTSIDE"],
    },
    {
        "id": "CLARIFY-PROJECT-01",
        "question": "phay contour ngoài 60x60x6",
        "defaults": False,
        "contains": ["Mình đã hiểu: contour chữ nhật outside 60x60 mm, sâu tổng 6 mm", "hệ tọa độ làm việc", "vị trí gốc phôi", "safe Z"],
        "not_contains": ["```gcode", "APPROVED"],
    },
    {
        "id": "CONFLICT-TOOL-01",
        "question": "phay contour ngoài 60x60x6 dao D10 G54 gốc trái dưới safe 10",
        "contains": ["Dao yêu cầu D10 không khớp dao active D6"],
        "not_contains": ["```gcode", "APPROVED"],
    },
    {
        "id": "AMBIGUOUS-01",
        "question": "phay ngoài 60",
        "contains": ["Mình chưa sinh G-code", "kiểu gia công/hình dạng"],
        "not_contains": ["```gcode", "APPROVED"],
    },
]


def evaluate() -> dict[str, Any]:
    from edge_backend.ai.agentic_gcode_response import try_agentic_gcode_response

    rows = []
    for scenario in SCENARIOS:
        ctx = context(defaults=scenario.get("defaults", True))
        calls: list[str] = []

        def tool(name: str, args: dict[str, Any]) -> str:
            calls.append(name)
            if name == "get_neo4j_context":
                return json.dumps(ctx, ensure_ascii=False)
            if name == "validate_gcode":
                return json.dumps({"valid": True, "passed": True, "warnings": [], "errors": []})
            raise AssertionError(name)

        with patch("edge_backend.ai.mcp_client_adapter.run_tool_via_configured_transport", tool):
            result = try_agentic_gcode_response(scenario["question"]) or ""
        failures = []
        for token in scenario.get("contains", []):
            if token not in result:
                failures.append(f"missing token: {token}")
        for token in scenario.get("not_contains", []):
            if token in result:
                failures.append(f"forbidden token: {token}")
        if "```gcode" in result and calls != ["get_neo4j_context", "validate_gcode"]:
            failures.append(f"wrong tool order: {calls}")
        rows.append({
            "id": scenario["id"],
            "question": scenario["question"],
            "passed": not failures,
            "failures": failures,
            "tool_order": calls,
        })
    passed = sum(row["passed"] for row in rows)
    return {
        "suite": "cnc-technical-assistant-generation-v2",
        "scope": "L2 service-free with mocked external context/validator transport",
        "total": len(rows),
        "passed": passed,
        "failed": len(rows) - passed,
        "pass_rate": passed / len(rows) if rows else 0.0,
        "machine_commands_issued": 0,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(ROOT / "reports/cnc_assistant_generation_eval_v2.json"))
    args = parser.parse_args()
    report = evaluate()
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ["suite", "total", "passed", "failed", "pass_rate"]}, ensure_ascii=False))
    if report["failed"]:
        for row in report["rows"]:
            if not row["passed"]:
                print(row["id"], row["failures"])
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
