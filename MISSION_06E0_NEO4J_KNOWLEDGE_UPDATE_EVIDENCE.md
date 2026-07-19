# MISSION 06E.0 — Neo4j Knowledge Graph Updater Evidence

## P0 — Freeze input
Inputs used:
- `LG_Display(1).zip`
- `Vinfast.zip`
- `AGENT_CLIENT_KNOWLEDGE_BASE_V1.md`
- `AGENT_CLIENT_CONTRACT_V1.json`
- `06B/06C/06D` foundation artifacts
- `cnc_knowledge_graph_seed.cypher`

## P1 — Goal Understanding
Goal: integrate the knowledge artifacts into the LG_Display project and create one main run file that updates Neo4j Aura/console.neo4j.io using `.env.example`.

## P2 — Inventory
Existing project already had Neo4j client/repository support and `neo4j` in requirements. The missing part was a one-command seeding/updating path and a packaged `agent_client_knowledge` data folder.

## P3 — Evaluation Matrix
| Scenario | Expected | Result |
|---|---|---|
| Dry-run update | Parses env/cypher and does not connect | PASS |
| Secret handling | Does not print full Neo4j password | PASS |
| File integration | Knowledge artifacts and seed cypher exist | PASS |
| Compatibility | Script creates `COMBINE`, `USES_TOOL`, `MACHINES` rels after seed | PASS by static review |
| Project structure | No runtime code path changed | PASS |

## P4 — Source-of-Truth Contract
- `.env.example`: Neo4j URI/user/password/database and seed defaults.
- `agent_client_knowledge/cnc_knowledge_graph_seed.cypher`: data source for Neo4j graph.
- `tools/update_neo4j_knowledge_base.py`: execution owner for update.
- Existing `neo4j_repo.py` remains unchanged and can read compatibility rels.

## P5 — Guardrails
- Do not print password.
- Do not modify frontend/cloud/edge runtime behavior.
- Do not expose network service; outbound Neo4j driver only.
- Default update is idempotent; destructive reset requires `--reset` flag.
- Live Neo4j update not claimed from sandbox.

## P6 — Files
- `agent_client_knowledge/AGENT_CLIENT_KNOWLEDGE_BASE_V1.md`
- `agent_client_knowledge/AGENT_CLIENT_CONTRACT_V1.json`
- `agent_client_knowledge/06B_USER_LEVEL_PROMPT_INTENT_CONTRACT_V1.md`
- `agent_client_knowledge/06B_USER_LEVEL_PROMPT_INTENT_CONTRACT_V1.json`
- `agent_client_knowledge/06C_CONTEXT_BUILDER_VALIDATOR_CONTRACT_V1.md`
- `agent_client_knowledge/06C_CONTEXT_BUILDER_VALIDATOR_CONTRACT_V1.json`
- `agent_client_knowledge/06D_AGENT_EVAL_HARNESS_SPEC_V1.md`
- `agent_client_knowledge/06D_AGENT_EVAL_HARNESS_SPEC_V1.json`
- `agent_client_knowledge/agent_eval_harness_v1.py`
- `agent_client_knowledge/eval_scenarios_v1.json`
- `agent_client_knowledge/cnc_knowledge_graph_seed.cypher`
- `agent_client_knowledge/README_UPDATE_NEO4J.md`
- `tools/update_neo4j_knowledge_base.py`
- `RUN_80_UPDATE_NEO4J_KNOWLEDGE.bat`
- `scripts/RUN_80_UPDATE_NEO4J_KNOWLEDGE.ps1`
- `integration_tests/test_mission06e_neo4j_update_static.py`
- `.env.example`

## P7 — Ultra-review
| Area | Result |
|---|---|
| Architecture | PASS — additive integration only |
| Existing runtime | PASS — no runtime logic modified |
| Neo4j | PASS — seed + compatibility updater added |
| Security | PASS — script masks password in terminal |
| Verification | PASS — dry-run and static tests pass |
| Real Neo4j write | NOT CLAIMED — must run on user machine |

## P8 — Handoff
Run:
```bat
RUN_80_UPDATE_NEO4J_KNOWLEDGE.bat
```
Then verify in Neo4j Browser:
```cypher
MATCH (n) RETURN labels(n)[0] AS loai, count(*) AS so_luong ORDER BY loai;
MATCH (r:OperatingRange) RETURN r.range_id, r.feed_min, r.feed_max, r.spindle_min, r.spindle_max ORDER BY r.range_id;
MATCH (:Tool)-[c:COMBINE]->(:Material) RETURN count(c) AS compat_combine_count;
```

## Command logs
### Command
```bash
/opt/pyvenv/bin/python -m py_compile tools/update_neo4j_knowledge_base.py integration_tests/test_mission06e_neo4j_update_static.py
```

cwd: `/mnt/data/work_m06e/lg/LG_Display/CNC5B/cnc_hmi_v18_A_3axis_CLEAN_READY`

exit code: `0`

stdout:
```text

```

stderr:
```text

```

### Command
```bash
/opt/pyvenv/bin/python tools/update_neo4j_knowledge_base.py --dry-run --env-file .env.example --cypher-file agent_client_knowledge/cnc_knowledge_graph_seed.cypher
```

cwd: `/mnt/data/work_m06e/lg/LG_Display/CNC5B/cnc_hmi_v18_A_3axis_CLEAN_READY`

exit code: `0`

stdout:
```text
=== Neo4j Knowledge Base Updater ===
Project root : /mnt/data/work_m06e/lg/LG_Display/CNC5B/cnc_hmi_v18_A_3axis_CLEAN_READY
Env file     : /mnt/data/work_m06e/lg/LG_Display/CNC5B/cnc_hmi_v18_A_3axis_CLEAN_READY/.env.example
Cypher file  : /mnt/data/work_m06e/lg/LG_Display/CNC5B/cnc_hmi_v18_A_3axis_CLEAN_READY/agent_client_knowledge/cnc_knowledge_graph_seed.cypher
Neo4j URI    : neo4j+s://f784a3c4.databases.neo4j.io
Neo4j user   : ********
Neo4j pass   : <configured>
Database     : neo4j
Active tool  : T1
Active mat   : Nhôm 6061
Seed statements         : 44
Compatibility statements: 7
Mode                   : DRY RUN
DRY RUN PASS — không kết nối Neo4j, không ghi dữ liệu.

```

stderr:
```text

```

### Command
```bash
pytest -q integration_tests/test_mission06e_neo4j_update_static.py
```

cwd: `/mnt/data/work_m06e/lg/LG_Display/CNC5B/cnc_hmi_v18_A_3axis_CLEAN_READY`

exit code: `0`

stdout:
```text
..                                                                       [100%]
2 passed in 2.12s

```

stderr:
```text

```
