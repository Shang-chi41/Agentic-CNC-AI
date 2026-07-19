# Mission 06E.0 — Update Neo4j Knowledge Graph

Mục tiêu: chạy **một file chính** để cập nhật dữ liệu Neo4j trên console.neo4j.io/AuraDB bằng thông tin trong `.env`.

## Cách chạy nhanh trên Windows

Từ thư mục project:

```bat
RUN_80_UPDATE_NEO4J_KNOWLEDGE.bat
```

Hoặc PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\RUN_80_UPDATE_NEO4J_KNOWLEDGE.ps1
```

## Cách chạy bằng Python

```bash
python tools/update_neo4j_knowledge_base.py --env-file .env --cypher-file agent_client_knowledge/cnc_knowledge_graph_seed.cypher
```

## Dry run không ghi dữ liệu

```bash
python tools/update_neo4j_knowledge_base.py --dry-run --env-file .env --cypher-file agent_client_knowledge/cnc_knowledge_graph_seed.cypher
```

## Verify-only sau khi cập nhật

```bash
python tools/update_neo4j_knowledge_base.py --verify-only --env-file .env
```

## File dữ liệu chính

- `agent_client_knowledge/cnc_knowledge_graph_seed.cypher`: seed Neo4j chính.
- `agent_client_knowledge/AGENT_CLIENT_CONTRACT_V1.json`: contract máy đọc được cho Agent Client.
- `agent_client_knowledge/AGENT_CLIENT_KNOWLEDGE_BASE_V1.md`: memory/contract cho người dùng đọc và cập nhật.

## Guardrails

- Script không in mật khẩu Neo4j ra terminal.
- Script không sửa frontend/cloud/edge runtime.
- Script chỉ kết nối outbound tới Neo4j bằng bolt/neo4j+s.
- Script tạo thêm compatibility relationship `COMBINE`, `USES_TOOL`, `MACHINES` để repo hiện có đọc được dữ liệu mà không cần sửa `neo4j_repo.py`.

## Sau khi chạy xong

Kiểm tra trong Neo4j Browser:

```cypher
MATCH (n) RETURN labels(n)[0] AS loai, count(*) AS so_luong ORDER BY loai;
MATCH (r:OperatingRange) RETURN r.range_id, r.feed_min, r.feed_max, r.spindle_min, r.spindle_max ORDER BY r.range_id;
MATCH (:Tool)-[c:COMBINE]->(:Material) RETURN count(c) AS compat_combine_count;
```
