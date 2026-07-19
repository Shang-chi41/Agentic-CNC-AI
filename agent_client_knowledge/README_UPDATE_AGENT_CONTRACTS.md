# RUN_81 — Phase 2: Update Agent Client Contracts to Neo4j

Sau khi `RUN_80_UPDATE_NEO4J_KNOWLEDGE.bat` đã tạo tầng machining KG, chạy:

```bat
RUN_81_UPDATE_AGENT_CLIENT_CONTRACTS.bat
```

Script này đọc các file contract:

- `AGENT_CLIENT_CONTRACT_V1.json`
- `06B_USER_LEVEL_PROMPT_INTENT_CONTRACT_V1.json`
- `06C_CONTEXT_BUILDER_VALIDATOR_CONTRACT_V1.json`
- `06D_AGENT_EVAL_HARNESS_SPEC_V1.json`

và tạo thêm tầng graph cho AI Agentic Client:

- `AgentClient`
- `AgentMission`
- `UserLevel`
- `PromptPolicy`
- `IntentContract`
- `IntentField`
- `ContextBuilderContract`
- `ValidatorContract`
- `ToolContract`
- `EvalHarness`
- `EvalMetric`
- `EvalScenario`
- `Guardrail`
- `SourceOfTruth`
- `ContractFile`

## Kiểm tra trong Neo4j Browser

```cypher
MATCH (n)
RETURN labels(n)[0] AS label, count(*) AS count
ORDER BY label;
```

```cypher
MATCH (:AgentClient {id:'AGENT_CLIENT_GCODE_V1'})-[r]->(n)
RETURN type(r) AS relationship, labels(n)[0] AS target_label, count(*) AS count
ORDER BY relationship, target_label;
```

```cypher
MATCH (:EvalHarness {id:'EVAL_HARNESS_06D_V1'})-[:HAS_METRIC]->(m:EvalMetric)
RETURN m.id, m.name, m.threshold
ORDER BY m.id;
```

```cypher
MATCH (:AgentClient {id:'AGENT_CLIENT_GCODE_V1'})-[:HAS_USER_LEVEL]->(u:UserLevel)
RETURN u.name, u.response_mode
ORDER BY u.name;
```

## Lưu ý an toàn

- Script không in mật khẩu Neo4j.
- Script không sửa frontend/cloud/edge runtime.
- Script không chạy G-code và không mở gate chạy máy thật.
- Đây là phase contract graph, không phải MCP integration.
