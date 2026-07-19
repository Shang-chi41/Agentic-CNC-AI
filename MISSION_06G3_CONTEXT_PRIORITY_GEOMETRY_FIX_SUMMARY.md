# Mission 06G3 — Context Priority Geometry Fix

## Root cause

The parser searched `context + current question`.  
When context contained machine metadata `400x300x100`, it selected `400x300` before the user's current `20x10`.

That is why the generator produced:

```text
X397 = 400 - tool_radius(3)
```

The actual bug was not G54/G55 and not unsafe 20 mm.  
It was context contamination: machine work volume became pocket geometry.

## Fix

Updated `edge_backend/ai/agentic_gcode_response.py` so safety-critical intent fields are parsed with this priority:

```text
current user question > context/chat history > machine metadata
```

Added source contract:

```text
agentic_execution_kit/19_AGENTIC_CURRENT_PROMPT_PRIORITY_CONTRACT.md
```

Added regression tests:

```text
integration_tests/test_mission06g3_context_priority_geometry.py
```

## Verified

```text
[32m.[0m[32m.[0m[32m.[0m[32m.[0m[32m.[0m[32m.[0m[32m.[0m[32m.[0m[32m.[0m[32m.[0m[32m.[0m[32m.[0m[32m.[0m[32m.[0m[32m                                                           [100%][0m
[32m[32m[1m14 passed[0m[32m in 0.20s[0m[0m
```

Frontend JS helper:

```text
PASS frontend/js/ai_chat.js
PASS frontend/js/api.js
PASS frontend/js/auth.js
PASS frontend/js/charts.js
PASS frontend/js/cnc_kinematics_multi_group.js
PASS frontend/js/control.js
PASS frontend/js/dashboard.js
PASS frontend/js/digital_twin.js
PASS frontend/js/history.js
PASS frontend/js/hmi_core.js
PASS frontend/js/hmi_redesign_v2.js
PASS frontend/js/hmi_state_presenter_v5.js
PASS frontend/js/monitor.js
PASS frontend/js/settings.js
PASS frontend/js/theme.js
Checked 15 JS files; failed=0
NODE CHECK PASS
```

## Not changed

- frontend API
- cloud route shape
- MCP server/tool logic
- 8 tool implementations
- machine-run gate
