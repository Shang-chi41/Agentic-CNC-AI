# Mission 25.4 Package Verification

## Verified

- Exact F1–F4 request parses to four features.
- Deliberately injected F550 and 0.5 mm step-down are detected.
- Deterministic regeneration preserves JobSpec SHA-256 and passes exact per-feature static validation.
- Worker sends only repaired artifact to MATLAB test double.
- Repaired first CHECK is not production eligible.
- Frontend invalidates stale artifact and requires exact hash reconfirmation.
- Chromium test proves stale Control QUEUE cannot save before reconfirmation.
- Missing Safe Z never exposes confirmation or CHECK actions.

## Terminal results

- `8 passed` — Python focused backend/worker/frontend wiring.
- `2 passed` — Chromium browser flows.
- `10 passed` — Node intent/hash gate.
- `95 passed` — relevant Mission 24–25 regression.
- `4/4 killed` — non-browser core dangerous mutations; source restored.

## Not verified

- Real MATLAB, NX MCD, Neo4j, OpenRouter, FluidNC or physical CNC.
- Full 64-file repository regression in this container.
- Browser navigation on deployed production origin.
- Arbitrary/manual G-code auto-repair without a confirmed JobSpec and process contract.
