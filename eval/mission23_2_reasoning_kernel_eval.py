#!/usr/bin/env python3
"""Deterministic Mission 23.2 reasoning-kernel evaluation (L2 only)."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from edge_backend.ai.deliberation_contract import (
    reasoning_mode_from_prompt,
    validate_deliberation_result,
)
from edge_backend.ai.feature_graph import parse_machining_request
from edge_backend.ai.teacher_orchestrator import plan_and_generate


def context(side=None, safe=None):
    data = {
        "machine": {"name": "EVAL_CNC", "work_volume_mm": "400x300x100"},
        "tool": {"name": "T1", "family": "END_MILL", "diameter_mm": 6,
                 "flute_length_mm": 20, "center_cutting": True,
                 "supported_entry_modes": ["plunge", "ramp", "helix"]},
        "material": {"name": "Aluminum 6061"},
        "operating_ranges": {"RECTANGULAR_CONTOUR_OUTSIDE": {
            "range_id": "OR_OUTSIDE", "feed_min": 600, "feed_max": 1200,
            "spindle_min": 14000, "spindle_max": 20000,
            "depth_max": 2.0, "stepover_ratio": 0.4,
        }},
    }
    if side is not None:
        data["setup"] = {"side_clearance_mm": side}
    if safe is not None:
        data["defaults"] = {"safe_z_mm": safe}
    return data


def request(safe=True):
    return ("Stock 60x64x8 mm Aluminum 6061. Mill outside rectangular contour "
            "50x54 depth 4 mm, center G54, Z0 stock top, T1 D6" +
            (", safe Z=5." if safe else "."))


def check(case_id, fn):
    try:
        evidence = fn()
        return {"id": case_id, "passed": True, "evidence": evidence, "error": ""}
    except Exception as exc:
        return {"id": case_id, "passed": False, "evidence": {},
                "error": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / "reports" / "MISSION23_2_REASONING_KERNEL_EVAL.json"))
    args = parser.parse_args()
    mission = ROOT / "agentic_execution_kit" / "MISSION_23_2_CROSS_LAYER_REASONING_33_SOURCE"
    results = []

    def c01():
        spec = parse_machining_request(request())
        assert spec.status == "READY" and "fixture.clearance" not in spec.ambiguities
        return {"status": spec.status}
    results.append(check("RK-01", c01))

    def c02():
        out = plan_and_generate(request(), neo4j_context=context(), max_candidates=1)
        assert out["status"] == "VALIDATED_DRAFT"
        assert out["authorization_blockers"] == ["fixture.clearance"]
        assert out["setup_requirements"][0]["required_clearance_mm"] == 1.0
        assert out["machine_authorized"] is False
        return {"decision": out["decision_record"]["decision"], "blockers": out["authorization_blockers"]}
    results.append(check("RK-02", c02))

    def c03():
        out = plan_and_generate(request(), neo4j_context=context(side=2), max_candidates=1)
        assert out["authorization_blockers"] == []
        assert any(x["claim"] == "fixture.clearance" for x in out["decision_record"]["retrieved_claims"])
        return {"decision": out["decision_record"]["decision"]}
    results.append(check("RK-03", c03))

    def c04():
        out = plan_and_generate(request(False), neo4j_context=context(safe=5), max_candidates=1)
        assert out["status"] == "VALIDATED_DRAFT" and out["job_spec"]["safe_z_mm"] == 5
        return {"safe_z": out["job_spec"]["safe_z_mm"]}
    results.append(check("RK-04", c04))

    def c05():
        out = plan_and_generate(request(False), neo4j_context=context(), max_candidates=1)
        assert out["status"] == "CONTEXT_REQUIRED" and out["gcode"] is None
        return {"issue": out["unresolved_context_issues"][0]["key"]}
    results.append(check("RK-05", c05))

    def c06():
        out = plan_and_generate(
            "Stock 80x60x17 mm Aluminum 6061. F1 circular feature diameter 30 center X0 Y0 depth 5. "
            "G54 center, Z0 stock top. Tool T1 D6. Safe Z=3.", neo4j_context=context())
        assert out["status"] == "NEEDS_CLARIFICATION"
        assert out["next_clarification"]["key"] == "F1.role"
        return {"question_key": out["next_clarification"]["key"]}
    results.append(check("RK-06", c06))

    def c07():
        spec = parse_machining_request(request().replace("G54", "G59.1"))
        assert spec.status == "INVALID" and spec.wcs == "G59.1"
        return {"errors": list(spec.errors)}
    results.append(check("RK-07", c07))

    def c08():
        valid = {"facts": [], "assumptions": [], "unknowns": [], "alternatives": [],
                 "checks": [], "decision": "PLAN", "concise_rationale": "grounded"}
        validate_deliberation_result(valid)
        try:
            validate_deliberation_result({**valid, "extra": 1})
        except ValueError:
            return {"strict_extra_rejected": True}
        raise AssertionError("extra field accepted")
    results.append(check("RK-08", c08))

    def c09():
        assert reasoning_mode_from_prompt("REASONING_MODE=RESEARCH\nTask") == "RESEARCH"
        return {"mode": "RESEARCH"}
    results.append(check("RK-09", c09))

    def c10():
        with (mission / "00_CONTROL" / "33_SOURCE_AGENT_SKILL_MATRIX.csv").open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 33 and len({r["source_id"] for r in rows}) == 33
        assert all(r["installed_in_cnc_runtime"] == "NO" for r in rows)
        return {"sources": len(rows)}
    results.append(check("RK-10", c10))

    def c11():
        data = json.loads((mission / "00_CONTROL" / "SKILL_LEASES.json").read_text(encoding="utf-8"))
        assert data["active_count"] == 0 and all(x["status"] == "CLOSED" for x in data["leases"])
        return {"leases": len(data["leases"]), "active": 0}
    results.append(check("RK-11", c11))

    def c12():
        env = (ROOT / ".env.example").read_text(encoding="utf-8")
        assert "OPENROUTER_REASONING_ENABLED=false" in env
        assert "OPENROUTER_REASONING_EXCLUDE=true" in env
        return {"reasoning_default": "disabled", "reasoning_visible": False}
    results.append(check("RK-12", c12))

    def c13():
        out = plan_and_generate(request(), neo4j_context=context(), max_candidates=1)
        assert out["decision_record"]["raw_chain_of_thought_stored"] is False
        return {"raw_chain_of_thought_stored": False}
    results.append(check("RK-13", c13))

    def c14():
        ref = "G21\nG90\nS17000 M3\nG1 Z-17 F600\nG1 X100 Y100 F9999\nM30\n"
        out = plan_and_generate(request(), neo4j_context=context(), max_candidates=1, reference_gcode=ref)
        assert out["reference_used_as_seed_only"] is True
        assert "X100" not in out["gcode"] and "F9999" not in out["gcode"]
        return {"seed_only": True}
    results.append(check("RK-14", c14))

    def c15():
        source = json.loads((mission / "00_CONTROL" / "SOURCE_REGISTRY_33.json").read_text(encoding="utf-8"))
        assert source["core_source_count"] == 33
        assert len(source["comparative_subsources"]) == 4
        return {"core_sources": 33, "comparative_subsources": 4}
    results.append(check("RK-15", c15))

    passed = sum(item["passed"] for item in results)
    report = {
        "schema": "mission23.2-reasoning-kernel-eval-v1",
        "scope": "L2 deterministic/sandbox only",
        "passed": passed,
        "total": len(results),
        "score": passed / len(results),
        "results": results,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"MISSION23.2 REASONING KERNEL EVAL: {passed}/{len(results)} score={report['score']:.3f}")
    for item in results:
        print(f"{item['id']}: {'PASS' if item['passed'] else 'FAIL'} {item['error']}")
    print(f"Report: {out}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
