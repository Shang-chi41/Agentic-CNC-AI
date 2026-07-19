# MISSION 06E.1 — RUN_81 Agent Client Contract Graph

## Goal

Bổ sung **Phase 2** cho Neo4j update:

```text
RUN_81_UPDATE_AGENT_CLIENT_CONTRACTS.bat
→ đọc 06A/06B/06C/06D contract JSON
→ cập nhật tầng Agent Client Contract Graph vào Neo4j
```

Phase 1 (`RUN_80`) tạo tầng machining KG: Machine/Axis/Tool/Operation/Material/OperatingRange/Alarm/Maintenance.

Phase 2 (`RUN_81`) tạo tầng Agentic Client: prompt đa trình độ, intent contract, context builder, validator, eval C1/C2/C3/C4, guardrails và source-of-truth.

## Files added

```text
RUN_81_UPDATE_AGENT_CLIENT_CONTRACTS.bat
scripts/RUN_81_UPDATE_AGENT_CLIENT_CONTRACTS.ps1
tools/update_neo4j_agent_contracts.py
agent_client_knowledge/README_UPDATE_AGENT_CONTRACTS.md
integration_tests/test_mission06e1_neo4j_agent_contracts_static.py
```

## What appears in Neo4j after RUN_81

Expected new labels:

```text
AgentClient
AgentMission
UserLevel
PromptPolicy
IntentContract
IntentField
ContextBuilderContract
ValidatorContract
ToolContract
EvalHarness
EvalMetric
EvalScenario
Guardrail
SourceOfTruth
ContractFile
```

Expected key counts:

```text
AgentClient              1
AgentMission             6
UserLevel                4
PromptPolicy             1
IntentContract           1
ContextBuilderContract   1
ValidatorContract        1
ToolContract             3
EvalHarness              1
EvalScenario             20
ContractFile             4
```

Some counts such as `IntentField`, `EvalMetric`, `Guardrail`, `SourceOfTruth` may grow if the contract files are extended later.

## How to run

Run phase 1 first if machining KG is not loaded yet:

```bat
RUN_80_UPDATE_NEO4J_KNOWLEDGE.bat
```

Then run phase 2:

```bat
RUN_81_UPDATE_AGENT_CLIENT_CONTRACTS.bat
```

Or PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\RUN_81_UPDATE_AGENT_CLIENT_CONTRACTS.ps1
```

## Verify in Neo4j Browser

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
MATCH (:AgentClient {id:'AGENT_CLIENT_GCODE_V1'})-[:HAS_USER_LEVEL]->(u:UserLevel)
RETURN u.name, u.response_mode
ORDER BY u.name;
```

```cypher
MATCH (:EvalHarness {id:'EVAL_HARNESS_06D_V1'})-[:HAS_METRIC]->(m:EvalMetric)
RETURN m.id, m.name, m.threshold
ORDER BY m.id;
```

```cypher
MATCH (:EvalHarness {id:'EVAL_HARNESS_06D_V1'})-[:HAS_SCENARIO]->(s:EvalScenario)
RETURN count(s) AS eval_scenario_count;
```

## Limitations

- Sandbox only verified dry-run/static tests.
- Real Neo4j write must be run on the user's machine using existing `.env.example` credentials.
- RUN_81 does not implement MCP yet; it only imports Agent Client contracts into Neo4j.
- RUN_81 does not execute G-code and does not open machine-run gate.
