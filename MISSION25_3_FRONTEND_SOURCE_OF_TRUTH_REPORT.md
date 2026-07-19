# Mission 25.3 — Frontend UserIntentContract Gate

Evidence level: **L2 — source inspection, pure-JS behavior tests, Python integration tests, injected context.**

## Root cause

The previous frontend rendered `FeatureGraph` only after the backend response, immediately exposed generated G-code, and called `setGCodeFromAI()` without an interpretation-confirmation checkpoint. Existing tests checked only that renderer names and fields existed.

## Implemented contract

1. Backend forwards `job_spec`, canonical JobSpec JSON, both SHA-256 hashes, semantic-clause accounting, pipeline status, authorization blockers and the exact per-feature OperatingRange contract.
2. Frontend displays UserIntentContract, clause→binding/disposition and ResolvedProcessContract before exposing G-code.
3. Missing values are shown as `CHƯA CÓ`; no silent `0` or `not-fixed` fallback.
4. A draft is confirmable only when status is `VALIDATED_DRAFT`, semantic clauses are fully accounted, context is found, deterministic validation passed and process-contract evidence exists.
5. The browser recomputes SHA-256 of canonical JobSpec JSON and G-code at confirmation time.
6. G-code is not loaded into Control preview before exact-hash confirmation.
7. CHECK/Save/Preview handlers independently revalidate the confirmed token.
8. Conditional drafts may be acknowledged as understood but cannot load into Control or expose actions while authorization blockers remain.

## Exact payload evidence

- Four-feature request without Safe Z: `CONTEXT_REQUIRED`, four features preserved, no G-code, frontend `confirmable=false`.
- Four-feature verified request: `VALIDATED_DRAFT`, four features preserved, seven semantic clauses, four process-contract rows, exact JobSpec/G-code hashes recomputed and matched, frontend `confirmable=true`, `actionEligible=true`.

## Verification

- Frontend source-of-truth audit: **10/10 PASS**.
- Pure Node contract tests: **9 PASS**.
- Frontend/backend wiring tests: **8 PASS**.
- Dangerous frontend mutations: **6/6 killed**, zero survivor/timeout.
- Full integration: **581 PASS across 62 files**, split into seven terminal groups.
- Python compile and JavaScript syntax checks: PASS.

## Limits retained

- Backend still generates the L2 draft before the frontend confirmation. The UI prevents exposure/use; it does not prevent generation.
- Confirmation is held in frontend memory and sent as metadata, but no backend confirmation record/ID is persisted or enforced against direct API clients.
- Real browser E2E interaction was not run; validation used pure JavaScript logic plus source/wiring tests.
- Live Neo4j, OpenRouter, MATLAB/NX, FluidNC and physical CNC remain `NOT_RUN`.

Therefore the verified claim is: **frontend exposure/use is fail-closed behind exact-hash interpretation confirmation in the tested code path. End-to-end authority is not yet complete.**
