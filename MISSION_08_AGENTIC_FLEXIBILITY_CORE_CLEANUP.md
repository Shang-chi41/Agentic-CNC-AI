# Mission 08 — Cleanup and Security

## Excluded from final packages

```text
.env
.venv/
.pytest_cache/
__pycache__/
*.pyc
*.pyo
application runtime logs
temporary duplicate verification logs
```

## Preserved

```text
source changes
workflow contracts
tests
evaluation scenarios
final evaluation JSON
final command logs
summary/evidence/handoff
```

## Secret handling

- The local `.env` is not included.
- API keys, passwords, tokens and JWTs are not written to evidence.
- The live provider evaluation is opt-in.
- The live evaluator does not call MATLAB/NX, FluidNC or machine actions.
