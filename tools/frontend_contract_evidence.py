from __future__ import annotations
import json
from unittest.mock import patch
from edge_backend.ai.agentic_response_harness import handle_agentic_request

NO_SAFE = (
    "Phôi 120 × 90 × 12 mm. Dao T1 END_MILL D6. "
    "F1: RECTANGULAR_CONTOUR_OUTSIDE 100 × 70 mm, sâu 4 mm. "
    "F2: CIRCULAR_POCKET Ø18, tâm X-30 Y0, sâu 3 mm. "
    "F3: CIRCULAR_POCKET Ø18, tâm X0 Y0, sâu 3 mm. "
    "F4: CIRCULAR_POCKET Ø18, tâm X30 Y0, sâu 3 mm."
)
VERIFIED = (
    "Phôi nhôm 6061 kích thước 100 × 80 × 12 mm. "
    "Dao T1 END_MILL D6. Safe Z 3 mm. "
    "F1: ROUNDED_RECT_POCKET 50 × 35 mm, R5, tâm X0 Y0, sâu 3 mm. "
    "F2: CIRCULAR_POCKET Ø12, tâm X-20 Y0, sâu 2 mm. "
    "F3: CIRCULAR_POCKET Ø12, tâm X20 Y0, sâu 2 mm. "
    "F4: RECTANGULAR_CONTOUR_OUTSIDE 80 × 60 mm, sâu 4 mm."
)
CTX = {
    "machine": {"name": "CNC", "work_volume_mm": "400x300x100"},
    "tool": {"name": "T1", "family": "END_MILL", "diameter_mm": 6, "flute_length_mm": 20,
             "center_cutting": True, "supported_entry_modes": ["plunge", "ramp", "helix"], "max_rpm": 24000},
    "material": {"name": "Aluminum 6061"},
    "operating_ranges": {
        "RECTANGULAR_CONTOUR_OUTSIDE": {"range_id": "OR_OUT", "feed_min": 600, "feed_max": 1200,
            "spindle_min": 14000, "spindle_max": 19000, "depth_max": 2.0, "stepover_ratio": 0.4},
        "CIRCULAR_POCKET": {"range_id": "OR_CP", "feed_min": 700, "feed_max": 1100,
            "spindle_min": 15000, "spindle_max": 19000, "depth_max": 2.0, "stepover_ratio": 0.4},
        "ROUNDED_RECT_POCKET": {"range_id": "OR_RP", "feed_min": 800, "feed_max": 1300,
            "spindle_min": 15000, "spindle_max": 19000, "depth_max": 3.0, "stepover_ratio": 0.55},
    },
}

def fake_transport(tool_name, arguments):
    assert tool_name == "get_neo4j_context"
    return json.dumps(CTX, ensure_ascii=False)

with patch("edge_backend.ai.mcp_client_adapter.run_tool_via_configured_transport", fake_transport):
    blocked = handle_agentic_request(NO_SAFE)
    verified = handle_agentic_request(VERIFIED)

for item in (blocked, verified):
    item["has_gcode"] = bool(item.get("gcode"))

out = {"blocked": blocked, "verified": verified}
with open('/mnt/data/MISSION25_3_FRONTEND_ACTUAL_PAYLOADS.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(json.dumps({
    "blocked": {"status": blocked.get("status"), "has_gcode": blocked["has_gcode"], "features": [x["id"] for x in blocked["job_spec"]["features"]]},
    "verified": {"status": verified.get("status"), "has_gcode": verified["has_gcode"], "features": [x["id"] for x in verified["job_spec"]["features"]],
                 "clauses": len(verified.get("semantic_clause_accounting") or []),
                 "process_features": len((verified.get("resolved_process_contract") or {}).get("features") or []),
                 "job_hash": verified.get("job_spec_sha256"), "gcode_hash": verified.get("gcode_sha256")}
}, ensure_ascii=False, indent=2))
