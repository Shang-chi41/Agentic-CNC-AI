#!/usr/bin/env python3
"""Service-free evaluation for the CNC technical-assistant language layer."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _same(actual: Any, expected: Any) -> bool:
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return abs(float(actual) - float(expected)) <= 1e-6
    return actual == expected


def evaluate(scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    from edge_backend.ai.agentic_gcode_response import missing_critical_fields, parse_gcode_intent
    from edge_backend.ai.operator_language import extract_dimensions

    rows = []
    for scenario in scenarios:
        kind = scenario["kind"]
        question = scenario["question"]
        intent = parse_gcode_intent(question, scenario.get("context"))
        actual = asdict(intent)
        failures: list[str] = []
        if kind == "parse":
            for key, expected in scenario.get("expect", {}).items():
                if not _same(actual.get(key), expected):
                    failures.append(f"{key}: expected={expected!r}, actual={actual.get(key)!r}")
        elif kind == "missing":
            missing = missing_critical_fields(intent, require_tool_material=False)
            for item in scenario.get("missing_contains", []):
                if item not in missing:
                    failures.append(f"missing field not reported: {item}")
        elif kind == "must_not_infer":
            dims = extract_dimensions(question)
            snapshot = asdict(dims)
            for key in scenario.get("must_not", []):
                if snapshot.get(key) is not None:
                    failures.append(f"unsafe inference {key}={snapshot.get(key)!r}")
        else:
            failures.append(f"unknown scenario kind: {kind}")
        rows.append({
            "id": scenario["id"],
            "kind": kind,
            "passed": not failures,
            "failures": failures,
            "question": question,
        })
    passed = sum(1 for row in rows if row["passed"])
    return {
        "suite": "operator-language-v2",
        "total": len(rows),
        "passed": passed,
        "failed": len(rows) - passed,
        "pass_rate": passed / len(rows) if rows else 0.0,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", default=str(ROOT / "eval/operator_language_scenarios_v2.json"))
    parser.add_argument("--output", default=str(ROOT / "reports/operator_language_eval_v2.json"))
    args = parser.parse_args()
    scenarios = json.loads(Path(args.scenarios).read_text(encoding="utf-8"))
    report = evaluate(scenarios)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ["suite", "total", "passed", "failed", "pass_rate"]}, ensure_ascii=False))
    if report["failed"]:
        for row in report["rows"]:
            if not row["passed"]:
                print(row["id"], row["failures"], row["question"])
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
