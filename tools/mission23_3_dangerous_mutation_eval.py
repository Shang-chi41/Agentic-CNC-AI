"""Run deterministic dangerous mutations against Mission 23.3 safety regressions.

The tool mutates only the isolated Mission 23.3 workspace, restores every file
in a finally block, and reports whether the selected regression suite killed
all safety-relevant mutants. It never changes the source package outside this
workspace.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
import os
import signal
from typing import Iterable


@dataclass(frozen=True)
class Mutation:
    mutation_id: str
    relative_path: str
    old: str
    new: str
    expected_guard: str
    tests: tuple[str, ...]


MUTATIONS = (
    Mutation(
        "MUT-UNSUPPORTED-GATE-REMOVED",
        "edge_backend/ai/feature_graph.py",
        'elif clause.safety_relevant and clause.disposition == "UNSUPPORTED":',
        'elif False and clause.safety_relevant and clause.disposition == "UNSUPPORTED":',
        "Known ontology limits must stop generation.",
        ("integration_tests/test_mission23_3_continuous_self_falsification.py::test_hidden_assumptions_fail_closed_with_specific_ontology_code",),
    ),
    Mutation(
        "MUT-UNACCOUNTED-GATE-REMOVED",
        "edge_backend/ai/feature_graph.py",
        'elif clause.safety_relevant and clause.disposition == "UNACCOUNTED":',
        'elif False and clause.safety_relevant and clause.disposition == "UNACCOUNTED":',
        "Unknown safety clauses must fail closed.",
        ("integration_tests/test_mission23_3_continuous_self_falsification.py::test_unrecognized_keepout_clause_is_unaccounted_and_blocks_generation",),
    ),
    Mutation(
        "MUT-COMPACT-DRILL-ACCEPTED-AS-ENDMILL",
        "edge_backend/ai/feature_graph.py",
        'if re.search(r"\\bdrill(?:ing)?\\b|mui\\s*khoan|khoan", _norm(text)):',
        'if False and re.search(r"\\bdrill(?:ing)?\\b|mui\\s*khoan|khoan", _norm(text)):',
        "Compact drill clauses must not become END_MILL tools.",
        ("integration_tests/test_mission23_3_guardrail_branch_inventory.py::test_remaining_parser_and_merge_control_flow_branches",),
    ),
    Mutation(
        "MUT-NO-TABS-NEGATION-DROPPED",
        "edge_backend/ai/feature_graph.py",
        '    if re.search(\n        r"(?:\\bno\\b|without|khong|không)\\s+(?:use\\s+)?(?:tabs?|cau\\s*giu|tai\\s*giu|onion\\s*skin)",',
        '    if False and re.search(\n        r"(?:\\bno\\b|without|khong|không)\\s+(?:use\\s+)?(?:tabs?|cau\\s*giu|tai\\s*giu|onion\\s*skin)",',
        "Negated retention strategy must remain negated.",
        ("integration_tests/test_mission23_3_continuous_self_falsification.py::test_no_tabs_is_not_misparsed_as_tabs_and_through_contour_remains_blocked",),
    ),
    Mutation(
        "MUT-AGENT-SELF-REPORT-TRUSTED",
        "edge_backend/ai/ambiguity_learning.py",
        '    "GOVERNANCE_AUDIT",\n}',
        '    "GOVERNANCE_AUDIT",\n    "AGENT_SELF_REPORT",\n}',
        "An agent may create a candidate but may not be its own oracle.",
        ("integration_tests/test_mission23_3_continuous_self_falsification.py::test_failure_learning_rejects_self_oracle_role_reuse_and_unreproduced_failure",),
    ),
    Mutation(
        "MUT-INDEPENDENT-REVIEW-SEPARATION-REMOVED",
        "edge_backend/ai/ambiguity_learning.py",
        '    if not reviewer or reviewer == case.reporter_role:',
        '    if not reviewer or (False and reviewer == case.reporter_role):',
        "Reviewer must be distinct from reporter.",
        ("integration_tests/test_mission23_3_continuous_self_falsification.py::test_failure_learning_rejects_self_oracle_role_reuse_and_unreproduced_failure",),
    ),
    Mutation(
        "MUT-REGRESSION-GREEN-GATE-REMOVED",
        "edge_backend/ai/ambiguity_learning.py",
        '    if not regression_green or not full_regression_passed:',
        '    if False and (not regression_green or not full_regression_passed):',
        "Promotion requires GREEN and full regression evidence.",
        ("integration_tests/test_mission23_3_continuous_self_falsification.py::test_failure_learning_rejects_failed_review_reused_approver_and_missing_green",),
    ),
)


def _tail(text: str, lines: int = 30) -> str:
    return "\n".join(text.splitlines()[-lines:])


def run(root: Path, out_path: Path) -> dict:
    results: list[dict] = []
    for mutation in MUTATIONS:
        path = root / mutation.relative_path
        original = path.read_text(encoding="utf-8")
        if original.count(mutation.old) != 1:
            raise RuntimeError(
                f"{mutation.mutation_id}: expected exactly one mutation target, "
                f"found {original.count(mutation.old)}"
            )
        try:
            path.write_text(original.replace(mutation.old, mutation.new, 1), encoding="utf-8")
            print(f"running {mutation.mutation_id}", flush=True)
            proc = subprocess.Popen(
                [sys.executable, "tools/pytest_force_exit.py", "-q", *mutation.tests],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                stdout, _ = proc.communicate(timeout=20)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                stdout, _ = proc.communicate()
                stdout += "\nMUTATION_TEST_TIMEOUT"
            killed = proc.returncode != 0
            results.append({
                "mutation_id": mutation.mutation_id,
                "file": mutation.relative_path,
                "expected_guard": mutation.expected_guard,
                "killed": killed,
                "pytest_exit_code": proc.returncode,
                "tests": list(mutation.tests),
                "output_tail": _tail(stdout),
            })
        finally:
            path.write_text(original, encoding="utf-8")
    killed = sum(item["killed"] for item in results)
    payload = {
        "schema": "mission23.3-dangerous-mutation-eval-v1",
        "mutants": len(results),
        "killed": killed,
        "survived": len(results) - killed,
        "mutation_score_percent": round(100.0 * killed / max(1, len(results)), 4),
        "complete": killed == len(results),
        "results": results,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    payload = run(args.root.resolve(), args.out.resolve())
    print(json.dumps({k: payload[k] for k in ("mutants", "killed", "survived", "mutation_score_percent", "complete")}))
    return 0 if payload["complete"] else 2


if __name__ == "__main__":
    code = main()
    try:
        sys.stdout.flush(); sys.stderr.flush()
    finally:
        os._exit(code)
