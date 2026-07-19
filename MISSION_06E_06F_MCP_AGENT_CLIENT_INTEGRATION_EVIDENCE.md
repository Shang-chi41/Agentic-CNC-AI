# Evidence — Mission 06E–06F

## Commands run

```bash
python eval/mcp_smoke_test.py
python -m compileall edge_backend mcp_server eval tools integration_tests
python -m pytest -q integration_tests/test_mission06e_neo4j_update_static.py integration_tests/test_mission06e1_neo4j_agent_contracts_static.py integration_tests/test_mission06e2_mcp_agent_client_static.py
python -m pytest -q integration_tests
python tools/update_neo4j_knowledge_base.py --dry-run --env-file .env --cypher-file agent_client_knowledge/cnc_knowledge_graph_seed.cypher
python tools/update_neo4j_agent_contracts.py --dry-run --env-file .env --knowledge-dir agent_client_knowledge
python eval/agent_eval_harness.py --traces agent_client_knowledge/sample_trace_logs_pass_v1.jsonl --out /tmp/agent_eval_report.json
```

## Results

```text
MCP SMOKE PASS
Tools: get_machine_status, get_latest_alarms, get_sensor_history, get_simulation_data, validate_gcode, check_gcode_simulation, get_gcode_result, get_neo4j_context
```

```text
compileall: PASS
```

```text
Mission 06E/06F focused tests: 12 passed
```

```text
Full integration tests: 110 passed
```

```text
RUN_80 dry-run: DRY RUN PASS — no Neo4j write
RUN_81 dry-run: DRY-RUN DONE — no Neo4j writes performed
```

```text
Sample eval report: C1=1.0, C2=1.0, C4=1.0, C3=N/A because no first-pass failures in sample pass traces
```

## Secret handling

- `.env` exists and contains real/local runtime values.
- `.env.example` is sanitized and should not carry real API keys/passwords.
- `.gitignore` excludes `.env` from source control.
- No secret values are printed in this evidence file.
