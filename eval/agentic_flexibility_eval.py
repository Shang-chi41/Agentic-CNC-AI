#!/usr/bin/env python3
"""Mission 08 Agentic flexibility evaluation harness.

Default mock mode is deterministic and service-free.  It evaluates routing,
intent, geometry semantics, tool order, repair limits, optimization invariants,
image routing and CHECK separation.  It never runs machine G-code.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


CTX = {
    "machine": {"name": "CNC", "work_volume_mm": "400x300x100"},
    "axes": [
        {"name": "X", "travel_mm": 400},
        {"name": "Y", "travel_mm": 300},
        {"name": "Z", "travel_mm": 100},
    ],
    "tool": {"name": "T1", "diameter_mm": 6, "max_rpm": 24000},
    "material": {"name": "Nhôm 6061"},
    "operating_range": {
        "range_id": "OR1",
        "feed_min": 600,
        "feed_max": 1500,
        "spindle_min": 14000,
        "spindle_max": 20000,
        "depth_min": 1.0,
        "depth_max": 3.0,
    },
}


def _json(data):
    return json.dumps(data, ensure_ascii=False)


def run_scenario(s):
    from edge_backend.ai.agentic_gcode_response import (
        GCodeIntent,
        parse_gcode_intent,
        try_agentic_gcode_response,
    )
    from edge_backend.ai.agentic_response_harness import (
        classify_request,
        generate_with_enforced_workflow,
        handle_agentic_request,
        review_or_optimize_gcode,
    )
    from edge_backend.ai.gcode_semantics import (
        normalize_program,
        pocket_swept_envelope_matches_comment,
    )
    from edge_backend.ai.gcode_static_validator import validate_gcode_static

    kind = s["kind"]

    if kind == "classify":
        actual = classify_request(
            s["question"], attached_gcode=s.get("gcode")
        ).task.value
        return actual == s["expected"], {"actual": actual}

    if kind in {"parse", "multi_turn"}:
        intent = parse_gcode_intent(s["question"], s.get("context"))
        actual = intent.__dict__
        expected = s["expect"]
        checks = []
        for key, value in expected.items():
            if key == "hole_count_parsed":
                checks.append(len(intent.hole_positions) == value)
            else:
                checks.append(actual.get(key) == value)
        return all(checks), {"actual": actual, "expected": expected}

    if kind == "deterministic_generate":
        def tool(name, args):
            if name == "get_neo4j_context":
                return _json(CTX)
            if name == "validate_gcode":
                return _json({"valid": True, "passed": True, "warnings": [], "errors": []})
            raise AssertionError(name)
        with patch(
            "edge_backend.ai.mcp_client_adapter.run_tool_via_configured_transport",
            tool,
        ):
            out = try_agentic_gcode_response(s["question"])
        ok = isinstance(out, str) and all(token in out for token in s["contains"])
        return ok, {"response_tail": str(out)[-1000:]}

    if kind == "clarification":
        out = handle_agentic_request(s["question"])
        ok = isinstance(out, str) and all(token in out for token in s["contains"])
        return ok, {"response": out}

    if kind == "percent":
        result = validate_gcode_static(
            s["gcode"],
            axis_limits_mm={"X": 200, "Y": 150, "Z": 50},
            operating_range={},
        )
        normalized, _ = normalize_program(s["gcode"])
        ok = not any("%" in w for w in result["warnings"]) and "%" not in normalized
        return ok, {"validation": result, "normalized": normalized}

    if kind == "swept_envelope":
        ok = pocket_swept_envelope_matches_comment(s["gcode"])
        return ok, {}

    if kind == "multiple_faults":
        result = validate_gcode_static(
            s["gcode"],
            axis_limits_mm={"X": 200, "Y": 150, "Z": 50},
            operating_range=CTX["operating_range"],
        )
        codes = {x["code"] for x in result["issues"]}
        expected = {
            "FORBIDDEN_M112", "AXIS_OUT_OF_RANGE",
            "SPINDLE_OUT_OF_RANGE", "FEED_OUT_OF_RANGE",
            "STEPDOWN_OUT_OF_RANGE",
        }
        return expected.issubset(codes), {"codes": sorted(codes)}

    if kind in {"repair_once", "repair_limit"}:
        calls = []
        validation_count = 0
        def tool(name, args):
            nonlocal validation_count
            calls.append(name)
            if name == "get_neo4j_context":
                return _json(CTX)
            if name == "validate_gcode":
                validation_count += 1
                if kind == "repair_once" and validation_count >= 2:
                    return _json({"valid": True, "passed": True, "errors": [], "warnings": []})
                return _json({"valid": False, "errors": ["F outside range"], "warnings": []})
            raise AssertionError(name)

        model_count = 0
        def model(prompt, context=None):
            nonlocal model_count
            model_count += 1
            feed = 1050 if kind == "repair_once" and model_count >= 2 else 50
            return {"gcode": (
                "G21\nG90\nG17\nG54\nT1 M6\nS17000 M3\n"
                f"G0 Z5\nG1 Z-3 F{feed}\nM30"
            )}

        intent = GCodeIntent(
            operation="milling", geometry="freeform_path",
            width_mm=20, material_name="Nhôm 6061", tool_name="T1",
            total_depth_mm=3, wcs="G54", origin="lower_left", safe_z_mm=5,
        )
        with patch(
            "edge_backend.ai.mcp_client_adapter.run_tool_via_configured_transport",
            tool,
        ), patch(
            "edge_backend.ai.provider_manager.provider_manager.ask_agentic",
            model,
        ):
            out, trace = generate_with_enforced_workflow(
                s["question"], None, intent, max_repairs=2
            )
        if kind == "repair_once":
            ok = (
                calls == ["get_neo4j_context", "validate_gcode", "validate_gcode"]
                and "repair×1" in out and "F1050" in out
            )
        else:
            ok = model_count == 3 and validation_count == 3 and "tối đa 2 vòng" in out
        return ok, {"calls": calls, "model_count": model_count, "response": out}

    if kind == "geometry_drift":
        def tool(name, args):
            return _json({"valid": True, "passed": True, "errors": [], "warnings": []})
        def model(prompt, context=None):
            return {"optimized_gcode": s["gcode"].replace("X17", "X27")}
        with patch(
            "edge_backend.ai.mcp_client_adapter.run_tool_via_configured_transport",
            tool,
        ), patch(
            "edge_backend.ai.provider_manager.provider_manager.ask_agentic",
            model,
        ):
            out = review_or_optimize_gcode(s["gcode"], optimize=True)
        return "Geometry invariants: BLOCKER" in out and "X27" not in out, {"response": out}

    if kind == "image_route":
        def tool(name, args):
            return _json(CTX)
        with patch(
            "edge_backend.ai.mcp_client_adapter.run_tool_via_configured_transport",
            tool,
        ):
            action = handle_agentic_request(s["question"], image_base64="abc")
        ok = (
            isinstance(action, dict)
            and action.get("action") == "image_to_gcode"
            and action.get("agentic_tool_trace") == ["get_neo4j_context"]
            and action.get("feed_rate") == 1050
        )
        return ok, {"action": action}

    if kind == "no_auto_check":
        def tool(name, args):
            if name == "get_neo4j_context":
                return _json(CTX)
            if name == "validate_gcode":
                return _json({"valid": True, "passed": True, "errors": [], "warnings": []})
            raise AssertionError(name)
        with patch(
            "edge_backend.ai.mcp_client_adapter.run_tool_via_configured_transport",
            tool,
        ):
            out = handle_agentic_request(s["question"])
        ok = "MATLAB/NX CHECK chưa chạy" in out and "check_gcode_simulation" not in out
        return ok, {"response_tail": out[-500:]}

    raise ValueError(f"Unknown scenario kind: {kind}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenarios",
        default=str(ROOT / "eval/agentic_flexibility_scenarios.json"),
    )
    parser.add_argument(
        "--out",
        default=str(ROOT / "reports/agentic_flexibility_eval.json"),
    )
    args = parser.parse_args()

    scenarios = json.loads(Path(args.scenarios).read_text(encoding="utf-8"))
    results = []
    metrics = defaultdict(lambda: {"passed": 0, "total": 0})

    for scenario in scenarios:
        try:
            passed, evidence = run_scenario(scenario)
            error = ""
        except Exception as exc:
            passed, evidence, error = False, {}, str(exc)
        results.append({
            "id": scenario["id"],
            "metric": scenario["metric"],
            "passed": passed,
            "error": error,
            "evidence": evidence,
        })
        metrics[scenario["metric"]]["total"] += 1
        metrics[scenario["metric"]]["passed"] += int(passed)

    metric_report = {}
    for name, count in metrics.items():
        score = count["passed"] / count["total"] if count["total"] else 0.0
        metric_report[name] = {**count, "score": score}

    overall_passed = sum(int(r["passed"]) for r in results)
    report = {
        "scenario_count": len(results),
        "passed": overall_passed,
        "failed": len(results) - overall_passed,
        "overall_score": overall_passed / len(results) if results else 0.0,
        "metrics": metric_report,
        "results": results,
        "claim_scope": "sandbox/mock evaluation; not live LLM/hardware certification",
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("AGENTIC FLEXIBILITY EVAL")
    print(f"Scenarios: {len(results)}")
    print(f"Passed: {overall_passed}")
    print(f"Failed: {len(results) - overall_passed}")
    print(f"Score: {report['overall_score']:.3f}")
    for name, data in sorted(metric_report.items()):
        print(f"{name}: {data['passed']}/{data['total']} = {data['score']:.3f}")
    print(f"Report: {out}")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
