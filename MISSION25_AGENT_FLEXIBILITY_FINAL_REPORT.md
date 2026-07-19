# MISSION 25 — Agent Flexibility and Clause Fidelity — Final L2 Report

## Scope

Mission 25 does not implement arbitrary transforms, per-feature tools or facing. It fixes two proven silent-understanding failures and one scalar conflict discovered during post-GREEN self-falsification:

1. A compound clause was marked `BOUND` when only one token had a JobSpec binding.
2. Standalone G68/whole-job transforms were dismissed as non-machining prose.
3. One tool ID declared with conflicting diameters silently selected the first diameter.

Human checkpoints were executed as `A/A/B/B`: root clause-fidelity fix, transform-group high-risk fix, multi-tool hard block, facing deferred.

## Implementation

- `edge_backend/ai/feature_graph.py`
  - semantic atom registry and partial-clause fail-closed accounting;
  - standalone high-risk transform classification;
  - distinct tool-ID detection with zero-padding normalization;
  - conflicting tool-diameter ambiguity detection;
  - one-tool/multiple-diameter clauses bind to the explicit conflict instead of disappearing;
  - unreachable duplicate diameter fallback removed.
- `integration_tests/test_mission25_agent_flexibility.py`
  - original eight F-M18 cases;
  - standalone G68 and Vietnamese `quay` transform;
  - multi-tool and same-tool diameter conflict;
  - tool capability, direct drilling guard and cut-direction tests;
  - supported-path and false-block controls.

CHECK/CONFIRM/RUN, approval engine, MATLAB/NX and FluidNC code were not changed.

## Evidence

- Baseline reproduction: 9 original failures reproduced with actual G-code/accounting.
- Post-patch probes: unrepresented qualifiers and transforms produce no draft; multi-tool is unsupported; conflicting diameter asks one question; supported requests still generate.
- Focused finite-core suite: **205 PASS**.
- Full integration: **558 PASS**, 59 files, 6 isolated groups, zero failure/error/terminal timeout.
- Statements: **1150/1150**.
- Branches: **586/586**.
- Guard inventory: **703 rows** = 586 branch arcs + 112 raise/return + 5 exception handlers; uncovered guard IDs = 0.
- Dangerous mutations: **4/4 killed**, survivors = 0, timeouts = 0.
- 33 source/method leases: all CLOSED; active = 0; runtime installs = 0.

## Controlled learning

F-M18, F-M20, the same-tool diameter conflict and Vietnamese transform synonym are recorded as `REPRODUCED` candidates. They are not self-promoted to durable truth; human approval remains required for memory promotion.

## Self-critique

The post-GREEN reviewer found two issues the original handoff did not close: same tool ID with different diameters, and the Vietnamese synonym `quay`. Both were added to RED/GREEN/mutation evidence before package closure.

Remaining Major limitation: semantic atom recognition is a finite vocabulary. Mission 25 proves current classes and fail-closed behavior, not complete understanding of every future natural-language qualifier. Open-world monitoring remains mandatory.

Remaining Minor limitation: the generic clarification text says “image and description conflict” even for two text declarations. Safety behavior is correct; UX wording is deferred because `clarification_planner.py` was outside the frozen source scope.

## Evidence boundary

```yaml
mission: MISSION25_AGENT_FLEXIBILITY
finite_guard_layer: COMPLETE_L2
clause_fidelity: VERIFIED_L2
open_world_robustness: CONTINUOUS_MONITORING
memory_promotion: PENDING_HUMAN_APPROVAL
multi_tool_execution: UNSUPPORTED
facing: UNSUPPORTED
Neo4j_live: NOT_RUN
OpenRouter_live: NOT_RUN
MATLAB_NX: NOT_RUN
FluidNC: NOT_RUN
physical_CNC: NOT_RUN
machine_authorized: false
```

## Key hashes

- Baseline `feature_graph.py`: `96d97c47499d226542fda2cb201b62ad2becf26113f9c4e2626991481cb325c0`
- Mission 25 `feature_graph.py`: `b0d8f454aa18049be5cadd1dcb2be473de3bc2b7c22f8d20c8bfa1e86090b9f9`
