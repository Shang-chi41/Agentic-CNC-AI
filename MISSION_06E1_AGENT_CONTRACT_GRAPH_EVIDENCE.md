# MISSION 06E.1 — Evidence

## Scope

Created RUN_81 Phase 2 updater for Agent Client Contract Graph.

No frontend/cloud/edge runtime source was changed. No G-code execution logic was changed.

## Files added

```text
RUN_81_UPDATE_AGENT_CLIENT_CONTRACTS.bat
scripts/RUN_81_UPDATE_AGENT_CLIENT_CONTRACTS.ps1
tools/update_neo4j_agent_contracts.py
agent_client_knowledge/README_UPDATE_AGENT_CONTRACTS.md
integration_tests/test_mission06e1_neo4j_agent_contracts_static.py
MISSION_06E1_AGENT_CONTRACT_GRAPH_SUMMARY.md
MISSION_06E1_AGENT_CONTRACT_GRAPH_EVIDENCE.md
```

## Verification run in sandbox

### Python compile

```bash
python3 -m py_compile tools/update_neo4j_agent_contracts.py
```

Result: PASS

### Dry-run

```bash
python3 tools/update_neo4j_agent_contracts.py --dry-run --knowledge-dir agent_client_knowledge
```

Result: PASS

Dry-run listed Phase 2 entities:

```text
AgentClient AGENT_CLIENT_GCODE_V1
AgentMission 06A..06F
UserLevel beginner/intermediate/expert/unknown
PromptPolicy PROMPT_POLICY_06B_V1
IntentContract 06B
IntentField ...
ContextBuilderContract 06C
ValidatorContract 06C
ToolContract get_neo4j_context / validate_gcode / generate_gcode
EvalHarness 06D
EvalMetric C1/C2/C3/C4...
EvalScenario S01..S20
SourceOfTruth ...
Guardrail ...
```

### Static integration tests

```bash
python3 -m pytest integration_tests/test_mission06e1_neo4j_agent_contracts_static.py -q
```

Result:

```text
3 passed
```

## Not claimed

- No real Neo4j write was performed in sandbox.
- No browser/console.neo4j.io screenshot was verified by the assistant.
- No MCP integration was implemented in this step.
- No machine/hardware runtime test was performed.

## Expected real-run verification after user runs RUN_81

Neo4j should show additional labels:

```text
AgentClient, AgentMission, UserLevel, PromptPolicy, IntentContract,
IntentField, ContextBuilderContract, ValidatorContract, ToolContract,
EvalHarness, EvalMetric, EvalScenario, Guardrail, SourceOfTruth, ContractFile
```

Important checks:

```cypher
MATCH (:AgentClient {id:'AGENT_CLIENT_GCODE_V1'})-[:HAS_USER_LEVEL]->(u:UserLevel)
RETURN u.name, u.response_mode ORDER BY u.name;
```

```cypher
MATCH (:EvalHarness {id:'EVAL_HARNESS_06D_V1'})-[:HAS_SCENARIO]->(s:EvalScenario)
RETURN count(s) AS eval_scenario_count;
```

Expected `eval_scenario_count = 20`.
