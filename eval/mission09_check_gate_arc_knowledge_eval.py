#!/usr/bin/env python3
"""Mission 09 evaluation: CHECK completion, gate/dataflow, arcs, and pattern RAG.

This is a sandbox/static evaluation. It never calls MATLAB/NX/FluidNC or the
machine-run gate.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def record(results, scenario, passed, evidence=None):
    results.append({
        "scenario": scenario,
        "passed": bool(passed),
        "evidence": evidence or {},
    })


def main() -> int:
    from edge_backend.ai.check_completion import packet_is_explicit_motion_complete
    from edge_backend.ai.agentic_gcode_response import try_agentic_gcode_response
    from edge_backend.ai.agentic_response_harness import handle_agentic_request
    from edge_backend.ai.gcode_pattern_learning import build_verified_pattern_candidate
    from edge_backend.ai.gcode_pattern_retriever import retrieve_patterns

    results = []

    record(results, "dispatch_100_percent_is_not_motion_done", not packet_is_explicit_motion_complete({
        "mode": "check", "check_id": "c1", "status": "running",
        "dispatch_progress": 1.0, "motion_complete": False,
    }, check_id="c1"))
    record(results, "wrong_check_id_is_not_done", not packet_is_explicit_motion_complete({
        "mode": "check", "check_id": "old", "status": "completed",
        "motion_complete": True, "success": True,
    }, check_id="c1"))
    record(results, "exact_motion_complete_is_done", packet_is_explicit_motion_complete({
        "mode": "check", "check_id": "c1", "status": "completed",
        "motion_complete": True, "success": True, "collision": False,
    }, check_id="c1"))

    node = subprocess.run(
        ["node", "integration_tests/mission09_toolpath_parser_test.mjs"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=30,
    )
    record(results, "g2_g3_arc_preview", node.returncode == 0, {
        "stdout": node.stdout.strip(), "stderr": node.stderr.strip(),
    })

    ctx = {
        "tool": {"name": "T1", "diameter_mm": 6},
        "material": {"name": "Nhôm 6061"},
        "operating_range": {
            "range_id": "OR1", "feed_min": 600, "feed_max": 1500,
            "spindle_min": 14000, "spindle_max": 20000,
            "depth_min": 1, "depth_max": 3,
        },
    }
    def tool(name, args):
        if name == "get_neo4j_context":
            return json.dumps(ctx, ensure_ascii=False)
        if name == "validate_gcode":
            return json.dumps({"valid": True, "passed": True, "errors": [], "warnings": []})
        raise AssertionError(name)

    centered_q = (
        "Phay túi chữ nhật 36x36, nhôm 6061, dao T1, sâu 3 mm, "
        "gốc G55 tại X0 Y0 ở giữa, safe Z=6 mm."
    )
    with patch(
        "edge_backend.ai.mcp_client_adapter.run_tool_via_configured_transport",
        tool,
    ):
        centered = try_agentic_gcode_response(centered_q)
    centered_ok = all(token in str(centered) for token in (
        "ORIGIN: G55 AT CENTER", "X-15", "X15", "Y-15", "Y15", "G0 Z6"
    ))
    record(results, "center_origin_t1_al6061", centered_ok, {"response_tail": str(centered)[-800:]})

    ambiguous = handle_agentic_request(
        "Phay nhôm 6061 hình chữ nhật 36x36, dao T1, sâu 3 mm, "
        "gốc G55 tại X0 Y0 ở giữa, safe Z=6 mm"
    )
    record(results, "ambiguous_rectangle_asks_pocket_or_contour",
           isinstance(ambiguous, str) and "túi kín hoặc contour trong/ngoài" in ambiguous)

    patterns = retrieve_patterns({"geometry": "circular_pocket", "operation": "milling"}, "túi tròn")
    record(results, "verified_pattern_rag_retrieval",
           bool(patterns) and patterns[0].get("verified") is True,
           {"pattern_ids": [p.get("pattern_id") for p in patterns]})

    gcode = """(RECTANGULAR POCKET 20x10 MM)
(TOOL DIAMETER: D6 MM)
G21
G90
G17
G54
T1 M6
S17000 M3
G0 X3 Y3 Z5
G1 Z-3 F1050
G1 X17 Y3 F1050
G1 X17 Y7 F1050
G1 X3 Y7 F1050
G1 X3 Y3 F1050
M30
"""
    rejected = False
    try:
        build_verified_pattern_candidate(gcode, {
            "static_valid": True, "motion_complete": False,
            "nx_collision": False, "operator_confirmed": True,
        })
    except ValueError:
        rejected = True
    record(results, "unverified_gcode_cannot_teach_agent", rejected)

    candidate = build_verified_pattern_candidate(gcode, {
        "static_valid": True, "motion_complete": True,
        "nx_collision": False, "operator_confirmed": True,
    })
    serialized = json.dumps(candidate, ensure_ascii=False)
    record(results, "verified_candidate_is_structural_not_numeric",
           candidate.get("promotion_status") == "HUMAN_REVIEW_REQUIRED"
           and "17000" not in serialized and "1050" not in serialized,
           {"candidate_id": candidate.get("candidate_id")})

    monitor = (ROOT / "frontend/js/monitor.js").read_text(encoding="utf-8")
    sim = (ROOT / "edge_backend/main_sim_only.py").read_text(encoding="utf-8")
    resolver = (ROOT / "edge_backend/runtime/dataflow_contract.py").read_text(encoding="utf-8")
    record(results, "sim_only_connectivity_is_not_check_or_machine_run",
           "SIM ONLY connectivity test đang hoạt động" in monitor
           and "resolve_runtime_dataflow(" in sim
           and '"mode": "pre_run_check"' in resolver
           and '"mode": "connectivity_test"' in resolver)

    passed = sum(int(r["passed"]) for r in results)
    report = {
        "scenario_count": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "score": passed / len(results) if results else 0,
        "scope": "sandbox/static/mock; no real MATLAB/NX/FluidNC/provider certification",
        "results": results,
    }
    out = ROOT / "reports/mission09_check_gate_arc_knowledge_eval.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("MISSION 09 EVAL")
    print(f"Scenarios: {len(results)}")
    print(f"Passed: {passed}")
    print(f"Failed: {len(results)-passed}")
    print(f"Score: {report['score']:.3f}")
    print(f"Report: {out}")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
