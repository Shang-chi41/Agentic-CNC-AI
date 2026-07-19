#!/usr/bin/env python3
"""Safe live Agentic evaluation on the operator machine.

This script exercises the configured MCP/Neo4j/validator and, only when the
operator explicitly allows it, the configured LLM provider.  It never calls
check_gcode_simulation, never talks to FluidNC, and never opens CHECK/Confirm.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
except Exception:
    pass


DETERMINISTIC_CASES = [
    {
        "id": "LIVE_RECT",
        "question": (
            "Phay túi chữ nhật 20x10 mm, nhôm 6061, dao T1, sâu 5 mm, "
            "gốc G54 tại góc trái dưới, safe Z=5 mm."
        ),
        "must_contain": ["```gcode", "RECTANGULAR POCKET 20x10", "Validate nhanh: PASS"],
    },
    {
        "id": "LIVE_CIRCLE_NO_ACCENT",
        "question": (
            "Phay tui hinh tron ban kinh 15 mm, nhom 6061, dao T1, sau 5 mm, "
            "goc G54 tai goc trai duoi, safe Z=5 mm."
        ),
        "must_contain": ["```gcode", "CIRCULAR POCKET R15", "G2"],
    },
    {
        "id": "LIVE_SLOT",
        "question": (
            "Phay rãnh 50x10 mm, nhôm 6061, dao T1, sâu 3 mm, "
            "gốc G54 tại góc trái dưới, safe Z=5 mm."
        ),
        "must_contain": ["```gcode", "SLOT 50x10", "Validate nhanh: PASS"],
    },
]


def _code_block(text: str) -> str:
    match = re.search(r"```gcode\s*\n(.*?)```", text or "", re.I | re.S)
    return match.group(1).strip() if match else ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--allow-provider-calls",
        action="store_true",
        help="Allow one external/configured LLM generation call.",
    )
    parser.add_argument(
        "--out",
        default=str(ROOT / "reports/agentic_flexibility_live_eval.json"),
    )
    args = parser.parse_args()

    from edge_backend.ai.agentic_response_harness import (
        WorkflowTrace,
        generate_with_enforced_workflow,
        handle_agentic_request,
    )
    from edge_backend.ai.agentic_gcode_response import parse_gcode_intent
    from edge_backend.ai.mcp_client_adapter import run_tool_via_configured_transport

    results: list[dict[str, Any]] = []

    # First prove the actual configured MCP/Neo4j transport.
    neo4j_raw = run_tool_via_configured_transport(
        "get_neo4j_context",
        {"tool_name": "T1", "material_name": "Nhôm 6061"},
    )
    try:
        neo4j = json.loads(neo4j_raw)
    except Exception:
        neo4j = {"error": "Invalid JSON"}
    neo4j_ok = not bool(neo4j.get("error")) and bool(neo4j.get("operating_range"))
    results.append({
        "id": "LIVE_NEO4J",
        "passed": neo4j_ok,
        "detail": {
            "tool": (neo4j.get("tool") or {}).get("name"),
            "material": (neo4j.get("material") or {}).get("name"),
            "range_id": (neo4j.get("operating_range") or {}).get("range_id"),
            "error": neo4j.get("error"),
        },
    })

    for case in DETERMINISTIC_CASES:
        try:
            response = handle_agentic_request(case["question"])
            code = _code_block(response if isinstance(response, str) else "")
            passed = (
                isinstance(response, str)
                and bool(code)
                and all(token in response for token in case["must_contain"])
                and "MATLAB/NX CHECK chưa chạy" in response
            )
            results.append({
                "id": case["id"],
                "passed": passed,
                "detail": {
                    "has_gcode": bool(code),
                    "response_tail": str(response)[-800:],
                },
            })
        except Exception as exc:
            results.append({
                "id": case["id"],
                "passed": False,
                "detail": {"error": str(exc)},
            })

    if args.allow_provider_calls:
        mixed_question = (
            "Phay túi chữ nhật 20x10 rồi khoan 2 lỗ X5 Y5 và X15 Y5, "
            "nhôm 6061, dao T1, sâu 3 mm, gốc G54 tại góc trái dưới, safe Z=5 mm."
        )
        intent = parse_gcode_intent(mixed_question)
        trace = WorkflowTrace()
        try:
            response, trace = generate_with_enforced_workflow(
                mixed_question, None, intent, max_repairs=2, trace=trace
            )
            code = _code_block(response)
            passed = (
                bool(code)
                and trace.tool_order
                and trace.tool_order[0] == "get_neo4j_context"
                and trace.tool_order[-1] == "validate_gcode"
            )
            results.append({
                "id": "LIVE_PROVIDER_MIXED",
                "passed": passed,
                "detail": {
                    "tool_order": trace.tool_order,
                    "active_provider": os.getenv("AI_PROVIDER", ""),
                    "response_tail": response[-1000:],
                },
            })
        except Exception as exc:
            results.append({
                "id": "LIVE_PROVIDER_MIXED",
                "passed": False,
                "detail": {
                    "tool_order": trace.tool_order,
                    "error": str(exc),
                },
            })
    else:
        results.append({
            "id": "LIVE_PROVIDER_MIXED",
            "passed": None,
            "detail": {
                "status": "SKIP",
                "reason": "Pass --allow-provider-calls to permit an external/configured LLM call.",
            },
        })

    evaluated = [r for r in results if r["passed"] is not None]
    passed_count = sum(bool(r["passed"]) for r in evaluated)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verification_level": "operator-machine live services",
        "safety": {
            "machine_commands_sent": False,
            "matlab_nx_check_called": False,
            "fluidnc_called": False,
        },
        "evaluated": len(evaluated),
        "passed": passed_count,
        "failed": len(evaluated) - passed_count,
        "overall": "PASS" if passed_count == len(evaluated) else "FAIL",
        "results": results,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "overall": report["overall"],
        "evaluated": report["evaluated"],
        "passed": report["passed"],
        "failed": report["failed"],
        "report": str(out),
    }, ensure_ascii=False, indent=2))
    return 0 if report["overall"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
