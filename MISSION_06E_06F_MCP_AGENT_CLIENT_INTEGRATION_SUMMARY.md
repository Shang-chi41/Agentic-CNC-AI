# Mission 06E–06F — MCP Tool Server + Agent Client Integration

## Scope

- 06E: tạo local stdio MCP-like Tool Server cho 8 tools hiện có.
- 06F: tích hợp Agent Client để provider_manager.ask_with_tools gọi tool qua MCP adapter, có fallback direct.
- Chuyển cấu hình thật từ `.env.example` sang `.env`; `.env.example` chỉ còn là mẫu không chứa secret.
- Sửa regression Cypher splitter: bỏ `//` và `/* ... */` comment trước khi split `;`.

## Source-of-truth

| Layer | Source-of-truth |
|---|---|
| Tool schema | `edge_backend/ai/tool_definitions.py` |
| Tool logic | `edge_backend/ai/tool_runner.py` |
| MCP tool execution | `mcp_server/cnc_tools_server.py` wraps `tool_runner.run_tool()` |
| Agent tool transport | `edge_backend/ai/mcp_client_adapter.py` |
| Agent loop | `edge_backend/ai/provider_manager.py` keeps `max_tool_rounds=5` |
| Env secrets | `.env` |
| Public sample env | `.env.example` non-secret only |
| Eval | `eval/agent_eval_harness.py`, `eval/mcp_smoke_test.py` |

## Files added

```text
mcp_server/__init__.py
mcp_server/cnc_tools_server.py
edge_backend/ai/mcp_client_adapter.py
eval/agent_eval_harness.py
eval/eval_scenarios_v1.json
eval/mcp_smoke_test.py
RUN_90_AGENT_MCP_SMOKE_TEST.bat
RUN_91_AGENT_EVAL_HARNESS.bat
scripts/RUN_90_AGENT_MCP_SMOKE_TEST.ps1
scripts/RUN_91_AGENT_EVAL_HARNESS.ps1
integration_tests/test_mission06e2_mcp_agent_client_static.py
.gitignore
.env
```

## Files changed

```text
.env.example
RUN_80_UPDATE_NEO4J_KNOWLEDGE.bat
RUN_81_UPDATE_AGENT_CLIENT_CONTRACTS.bat
scripts/RUN_80_UPDATE_NEO4J_KNOWLEDGE.ps1
scripts/RUN_81_UPDATE_AGENT_CLIENT_CONTRACTS.ps1
tools/update_neo4j_knowledge_base.py
edge_backend/ai/provider_manager.py
edge_backend/ai/providers/_system_prompt.py
edge_backend/ai/tool_definitions.py
edge_backend/ai/gcode_validator.py
edge_backend/database/repositories/neo4j_repo.py
integration_tests/test_mission06e_neo4j_update_static.py
integration_tests/test_mission05b2_architecture_regression_static.py
```

## How to run

### MCP smoke test

```bat
RUN_90_AGENT_MCP_SMOKE_TEST.bat
```

Expected:

```text
MCP SMOKE PASS
Tools: get_machine_status, ..., get_neo4j_context
```

### Agent eval harness sample

```bat
RUN_91_AGENT_EVAL_HARNESS.bat
```

This evaluates sample traces only; it does not call an LLM or machine hardware.

### Neo4j updates

```bat
RUN_80_UPDATE_NEO4J_KNOWLEDGE.bat
RUN_81_UPDATE_AGENT_CLIENT_CONTRACTS.bat
```

Both now use `.env` by default.

## Acceptance status

| Requirement | Status |
|---|---|
| MCP server local stdio, no network exposure | PASS |
| tools/list returns 8 tools | PASS |
| tools/call wraps existing `tool_runner.run_tool()` | PASS |
| ProviderManager calls tools via MCP adapter | PASS |
| Direct fallback if MCP unavailable | PASS |
| `max_tool_rounds=5` preserved | PASS |
| `.env` created and `.env.example` sanitized | PASS |
| Cypher comment-splitting regression fixed | PASS |
| Static/integration tests | PASS: 110 tests |

## Limitations

- I did not call real external LLM APIs from the sandbox.
- I did not connect to real Neo4j/FluidNC/MATLAB/NX runtime from the sandbox.
- The included agent eval run uses sample traces; real C1/C2/C3/C4 must be measured from real Agent Client trace logs after you run the LLM path.
- The final ZIP intentionally contains `.env` because you requested API keys/config move there. Do not commit `.env` to Git.
