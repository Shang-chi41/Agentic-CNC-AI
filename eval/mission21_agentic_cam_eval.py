#!/usr/bin/env python3
"""Deterministic Mission 21 evaluation inspired by DeepEval/RAGAS/Autoresearch.

No online model is required. The harness measures observable behavior:
clarification, tool correctness, feature coverage, context precision,
faithfulness/provenance, candidate comparison and machine-authority blocking.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from edge_backend.ai.attachment_contract import validated_gcode_attachment
from edge_backend.ai.endmill_guardrails import validate_endmill_only_gcode
from edge_backend.ai.feature_graph import ALLOWED_OPERATIONS, parse_machining_request
from edge_backend.ai.reference_gcode_seed import extract_reference_seed
from edge_backend.ai.semantic_job_validator import validate_gcode_against_job_spec
from edge_backend.ai.teacher_orchestrator import plan_and_generate_spec


def context_for(spec):
    ranges = {}
    for op in sorted({f.operation for f in spec.features if f.operation and f.operation != "REFERENCE_ONLY"}):
        ranges[op] = {
            "range_id": {
                "SLOT_MILL": "OR_SLOT",
                "CROSS_SLOT_MILL": "OR_CROSS_SLOT",
                "CIRCULAR_THROUGH_MILL": "OR_CIRCLE_THROUGH",
            }.get(op, f"OR_{op}"),
            "feed_min": 500,
            "feed_max": 1200,
            "spindle_min": 14000,
            "spindle_max": 19000,
            "depth_max": 3.0,
            "stepover_ratio": 0.45,
        }
    return {
        "machine": {"name": "EVAL_CNC", "work_volume_mm": "400x300x100"},
        "tool": {
            "name": spec.tool.tool_id,
            "family": "END_MILL",
            "diameter_mm": spec.tool.diameter_mm,
            "flute_length_mm": 30,
            "center_cutting": True,
            "supported_entry_modes": ["plunge", "ramp", "helix"],
        },
        "material": {"name": spec.stock.material},
        "operating_ranges": ranges,
    }


def run_case(case):
    kind = case.get("kind", "job")
    evidence = {}
    if kind == "forbidden_gcode":
        result = validate_endmill_only_gcode(case["gcode"])
        passed = not result.passed and case["expect_code"] in result.codes
        return passed, {"codes": result.codes, "errors": result.errors}
    if kind == "reference_seed":
        seed = extract_reference_seed(case["gcode"])
        passed = all(field not in seed for field in case["forbid_seed_fields"])
        return passed, seed
    if kind == "attachment":
        digest = hashlib.sha256(case["gcode"].encode()).hexdigest()
        payload = validated_gcode_attachment(case["gcode"], case["filename"], digest)
        passed = payload["sha256"] == digest and payload["gcode"] == case["gcode"]
        return passed, payload

    spec = parse_machining_request(case["request"])
    context = context_for(spec)
    result = plan_and_generate_spec(spec, neo4j_context=context, max_candidates=3)
    expected = case.get("expect_status")
    passed = result.get("status") == expected if expected else True
    evidence.update({
        "status": result.get("status"),
        "ambiguities": result.get("ambiguities"),
        "errors": result.get("errors"),
        "job_spec_sha256": result.get("job_spec_sha256"),
        "selected_strategy": result.get("selected_strategy"),
        "machine_authorized": result.get("machine_authorized"),
    })
    if case.get("expect_ambiguity"):
        passed = passed and case["expect_ambiguity"] in (result.get("ambiguities") or [])
    if case.get("expect_error"):
        passed = passed and any(case["expect_error"] in error for error in result.get("errors") or spec.errors)
    if expected == "VALIDATED_DRAFT":
        gcode = result.get("gcode") or ""
        semantic = validate_gcode_against_job_spec(gcode, spec)
        guard = validate_endmill_only_gcode(gcode)
        expected_ids = set(case.get("expect_features") or [f.id for f in spec.features])
        passed = passed and semantic.passed and guard.passed
        passed = passed and expected_ids.issubset(set(semantic.covered_feature_ids))
        passed = passed and result.get("machine_authorized") is False and result.get("check_status") == "NOT_RUN"
        # RAGAS-style deterministic grounding proxies.
        required_ops = {f.operation for f in spec.features if f.operation and f.operation != "REFERENCE_ONLY"}
        retrieved_ops = set(context["operating_ranges"])
        context_precision = len(required_ops & retrieved_ops) / max(1, len(retrieved_ops))
        context_recall = len(required_ops & retrieved_ops) / max(1, len(required_ops))
        range_faithful = all(f"(RANGE={context['operating_ranges'][op]['range_id']}" in gcode for op in required_ops)
        passed = passed and context_precision == 1.0 and context_recall == 1.0 and range_faithful
        evidence.update({
            "semantic_errors": semantic.errors,
            "covered": semantic.covered_feature_ids,
            "candidate_count": len(result.get("candidates") or []),
            "context_precision": context_precision,
            "context_recall": context_recall,
            "range_faithful": range_faithful,
        })
    if case.get("expect_min_candidates"):
        candidates = [c for c in result.get("candidates") or [] if c.get("valid")]
        scores = [c["metrics"]["score"] for c in candidates]
        selected = next((c for c in candidates if c["candidate_id"] == result.get("selected_candidate_id")), None)
        passed = passed and len(candidates) >= int(case["expect_min_candidates"])
        passed = passed and selected is not None and selected["metrics"]["score"] == min(scores)
    if case.get("expect_range"):
        passed = passed and f"(RANGE={case['expect_range']}" in (result.get("gcode") or "")
    return passed, evidence


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default=str(ROOT / "eval/mission21_agentic_cam_cases.json"))
    parser.add_argument("--out", default=str(ROOT / "reports/MISSION21_AGENTIC_CAM_EVAL.json"))
    args = parser.parse_args()
    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    results = []
    for case in cases:
        try:
            passed, evidence = run_case(case)
            error = ""
        except Exception as exc:
            passed, evidence, error = False, {}, f"{type(exc).__name__}: {exc}"
        results.append({"id": case["id"], "category": case["category"], "passed": passed, "error": error, "evidence": evidence})
    categories = {}
    for result in results:
        bucket = categories.setdefault(result["category"], {"passed": 0, "total": 0})
        bucket["total"] += 1
        bucket["passed"] += int(result["passed"])
    passed_count = sum(int(r["passed"]) for r in results)
    report = {
        "schema": "mission21-agentic-cam-eval-v1",
        "method_sources": ["DeepEval behavioral metrics", "RAGAS grounding metrics", "Autoresearch candidate comparison", "Guardrails deterministic validation"],
        "scope": "END_MILL_ONLY L2",
        "score": passed_count / max(1, len(results)),
        "passed": passed_count,
        "total": len(results),
        "categories": categories,
        "results": results,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"MISSION21 AGENTIC CAM EVAL: {passed_count}/{len(results)} score={report['score']:.3f}")
    for name, stats in categories.items():
        print(f"{name}: {stats['passed']}/{stats['total']}")
    print(f"Report: {out}")
    return 0 if passed_count == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
