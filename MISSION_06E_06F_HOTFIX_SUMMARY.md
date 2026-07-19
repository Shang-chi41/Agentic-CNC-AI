# Mission 06E/06F Hotfix Summary

## Fixed issues

1. `RUN_00_LOCAL_VERIFY.ps1` no longer treats normal native stderr logs as terminating `NativeCommandError`.
2. Windows `cp1252` subprocess capture no longer crashes Mission 6 dry-run/MCP smoke test on Vietnamese text.
3. AI chat response policy now blocks leaked reasoning and unsafe G-code assumptions for beginner/unknown users.

## What changed

- Added UTF-8 stdio configuration to Mission 6 subprocess scripts.
- Added MCP unknown-tool ASCII-safe error text.
- Added `edge_backend/ai/agent_response_policy.py`.
- Integrated response policy into `edge_backend/workers/ai_worker.py`.
- Strengthened CNC system prompt: no hidden reasoning, no assumed geometry/origin.
- Added regression tests.

## Verification

```text
compileall: PASS
RUN_80 dry-run: PASS
MCP smoke: PASS
Focused Mission 06E/06F hotfix tests: 13 passed
```

## Important limitation

This was verified in sandbox/static/subprocess mode. It does not prove real LLM API, browser frontend, MongoDB runtime, FluidNC, MATLAB, or NX MCD runtime stability on your machine.
