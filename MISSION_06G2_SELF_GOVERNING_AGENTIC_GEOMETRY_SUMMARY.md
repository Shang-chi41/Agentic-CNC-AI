# Mission 06G2 — Self-Governing Workflow + Agentic Geometry Guard

## What changed

1. Updated project-level workflow:
   - `AGENTIC_RUN_FIRST.md`
   - `agentic_execution_kit/17_SELF_GOVERNING_WORKFLOW_LOCK.md`
   - `agentic_execution_kit/18_AGENTIC_GCODE_GEOMETRY_CONTRACT.md`

2. Added a local geometry guard inside:
   - `edge_backend/ai/agentic_gcode_response.py`

3. Added regression tests:
   - `integration_tests/test_mission06g2_agentic_geometry_contract.py`

## Why

The recurring failure was not only a code bug. It was a workflow failure:
- not locking source-of-truth before patching;
- not testing exact user prompt;
- not preventing user geometry from being confused with machine travel.

## Source-of-truth locked

```text
User geometry 20x10 mm = pocket size.
Machine travel 400x300 mm = limit only.
T1 diameter 6 mm = radius offset 3 mm.
Allowed tool-center envelope = X3..X17, Y3..Y7.
```

## Not changed

- frontend API shape
- cloud AI route shape
- MCP tool logic
- 8 existing tools
- machine-run gate
