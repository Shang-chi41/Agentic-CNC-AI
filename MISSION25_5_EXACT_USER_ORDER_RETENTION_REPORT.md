# Mission 25.5 — Exact User Order and Retention Hotfix

## Failure reproduced

The exact browser input was rejected with:

- `unaccounted_semantic_clause:C011`
- `unaccounted_semantic_clause:C012`

Root causes:

1. The clause splitter cut `F4 được gia công sau F1, F2 và F3` at the comma before `F2`, producing two false clauses.
2. `MachiningJobSpec` had no explicit feature dependency field, so the requested operation order could not be preserved.
3. `Chi tiết được gá giữ bên ngoài trong toàn bộ quá trình` was not recognized as a retention contract and was incorrectly treated as non-machining prose.
4. Earlier browser verification used a shortened F1–F4 example that omitted these two clauses, so it did not test the user's exact request.

## Contract changes

- Added `Feature.predecessor_ids` to the canonical JobSpec.
- Parsed the exact order clause as `F4 <- F1,F2,F3`.
- Added validation for unknown predecessors, self-dependencies and cycles.
- Candidate generation now performs a stable topological sort constrained by the declared dependencies.
- Semantic validation rejects G-code whose feature-block order violates the JobSpec.
- Added `EXTERNAL_FIXTURE` retention parsing for the exact Vietnamese phrase.
- Semantic accounting now binds the two clauses instead of ignoring or splitting them.

## Exact public-flow result

- Status: `VALIDATED_DRAFT`
- C011: `BOUND -> feature_order:F4<-F1,F2,F3`
- C012: `BOUND -> part.retention`
- Generated feature-block order: `F2, F3, F1, F4`
- F4 is after F1, F2 and F3.
- Static validator: PASS
- Semantic validator: PASS

## Verification

- 5 exact order/retention regressions: PASS
- 15 focused backend + frontend + Chromium tests: PASS
- 102 Mission 24–25 relevant regressions: PASS
- Exact `agentic_response_harness.handle_agentic_request()` public flow: PASS

## Evidence level and limitations

L2 only. Neo4j context is deterministic test context. MATLAB/NX/FluidNC and physical machining were not run. The full repository suite was attempted, but one legacy test process did not terminate cleanly after printing its PASS summary, so no full-suite PASS is claimed.
