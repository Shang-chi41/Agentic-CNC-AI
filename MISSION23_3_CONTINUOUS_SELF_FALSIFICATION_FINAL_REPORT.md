# Mission 23.3 — Continuous Self-Falsification Final Report

Status: `FINITE_GUARD_LAYER_COMPLETE_L2__OPEN_WORLD_CONTINUOUS_MONITORING`.

## Mission contract

Mission 23.3 separates three obligations that must not be collapsed into a single PASS:

1. Prove measurable coverage of the finite guardrail code in `feature_graph.py`, `semantic_job_validator.py`, and `teacher_orchestrator.py`.
2. Fail closed when a safety-relevant user clause cannot be represented or has not been accounted for.
3. Convert real failures into reviewed learning candidates; never let the agent self-promote a report into a durable rule.

Completeness is a continuing convergence process. Only the finite guard layer is eligible for a technical COMPLETE state.

## 1. Finite guard coverage

The inventory is generated from Python AST, coverage.py branch arcs, test contexts, terminal `raise`/`return` points, and explicit exception handlers.

| Measure | Result |
|---|---:|
| Statements in three target files | 1095/1095 |
| Branch arcs | 566/566 |
| Raise/return points | 105/105 |
| Exception handlers | 5/5 |
| Guard inventory rows | 676 |
| Uncovered guard IDs | 0 |
| Coverage status | COMPLETE |

Every inventory row maps to an expected outcome, a forbidden outcome, and one or more executable test contexts in `EXPECTED_FORBIDDEN_MATRIX.csv`.

## 2. Open-world fail-closed behavior

`MachiningJobSpec` now contains semantic clause accounting. Every parsed clause receives a disposition such as `BOUND`, `UNSUPPORTED`, `UNACCOUNTED`, or `IGNORED_WITH_JUSTIFICATION`.

Safety-relevant `UNSUPPORTED` or `UNACCOUNTED` clauses block candidate generation before G-code is produced. Stable unsupported reasons currently cover:

- cylindrical stock geometry;
- feature-local datum references;
- chamfer capability not represented by the current tool/kinematic model;
- pre-existing void topology;
- explicit asymmetric layer schedules;
- directed toolpath-strategy constraints not supported by the planner;
- feature-scoped Safe Z;
- material-state sequencing and retention dependencies.

Unknown safety clauses that do not match a known unsupported category produce `UNACCOUNTED_SEMANTIC_CLAUSE`, not a best-effort G-code draft.

`fixture.clearance` remains a deferred setup and authorization requirement: a conditional draft may be generated, but CHECK/Confirm/RUN remain blocked until the fixture fact is resolved.

## 3. Controlled failure learning

A failure learning case follows the append-only lifecycle:

```text
OBSERVED
→ REPRODUCED
→ RULE_PROPOSED
→ REVIEWED
→ REGRESSION_PROTECTED
```

Required controls:

- accepted observations come only from `OPERATOR_REPORT`, `RUNTIME_MONITOR`, `HUMAN_AUDIT`, or `GOVERNANCE_AUDIT`;
- agent self-reports cannot enter the trusted lifecycle;
- the source evidence SHA-256 must match;
- reporter, independent reviewer, and approver must be role-separated;
- approval requires GREEN evidence and full regression;
- ledger history is append-only and status rollback is rejected.

The silent semantic-drop failure reported by the user was reproduced, reviewed independently, approved under the mission owner directive, implemented, and regression protected. The complete history is stored in `FAILURE_LEARNING_LEDGER.jsonl`.

## 4. Dangerous mutation evidence

Seven deliberate safety mutations were injected one at a time and all were killed by the regression suite:

- remove unsupported-clause gate;
- remove unaccounted-clause gate;
- accept compact drill text as an end mill;
- break `no tabs` negation;
- accept agent self-report as trusted evidence;
- remove independent-review role separation;
- remove the GREEN/full-regression approval gate.

Mutation score: **7/7 = 100%** for this declared dangerous-mutant set. This is not a claim that all possible mutations have been enumerated.

## 5. Regression evidence

- Focused finite-guard coverage run: **162 PASS**.
- Full integration suite: **494 PASS** across 57 test files in 10 isolated groups.
- Python compileall: **PASS**.
- Group timeout/failure count: **0**.

The grouped runner forces process termination after pytest completes so lingering background threads cannot hide the real exit code.

## 6. 33-source governance

All 33 core sources were mapped to a mission-specific agent, bounded skill/method lease, allowed scope, prohibition, and cleanup requirement. No upstream plugin or repository was installed into CNC runtime. All leases are `CLOSED`; active count is `0`.

The sources support the process but do not gain authority over project contracts, deterministic validators, runtime evidence, or operator authorization.

## 7. Independent review

Blocker/Critical findings after regression and mutation campaigns: **0**.

Closed findings:

- exception handlers were missing from the first finite inventory;
- compact drill fallback bypassed clause-level exclusion;
- represented-field validation allowed silent semantic drops;
- learning lacked explicit reporter/reviewer/approver separation.

All four were fixed and regression protected.

## 8. Explicit limitations

Mission 23.3 does not claim complete natural-language or physical CNC ontology coverage. Unsupported cases are deliberately blocked rather than planned. The open-world campaign ledger remains active and must continue to record discovery yield, false-allow, false-block, wrong-reason, and new semantic-drop classes.

Evidence level is **L2** only. Live OpenRouter, live Neo4j, MATLAB/NX, FluidNC, and physical machine verification are `NOT_RUN`. `machine_authorized` remains false; CHECK and operator Confirm remain mandatory.

## Final state

```yaml
finite_guard_coverage:
  status: COMPLETE_L2
  statement_coverage: 100%
  branch_arc_coverage: 100%
  terminal_coverage: 100%
  exception_handler_coverage: 100%
  uncovered_guard_ids: 0

open_world_robustness:
  status: CONTINUOUS_MONITORING
  policy: FAIL_CLOSED
  silent_semantic_drop_allowed: false

failure_learning:
  status: CONTROLLED
  self_promotion_allowed: false
  independent_review_required: true
  human_approval_required: true

runtime:
  OpenRouter: NOT_RUN
  Neo4j: NOT_RUN
  MATLAB_NX: NOT_RUN
  FluidNC: NOT_RUN
  physical_CNC: NOT_RUN
```
