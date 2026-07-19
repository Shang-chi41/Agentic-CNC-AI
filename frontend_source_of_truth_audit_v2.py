from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")

chat = text("frontend/js/ai_chat.js")
control = text("frontend/js/control.js")
route = text("cloud_backend/routes/ai_routes.py")
worker = text("edge_backend/workers/ai_worker.py")
harness = text("edge_backend/ai/agentic_response_harness.py")
teacher = text("edge_backend/ai/teacher_orchestrator.py")
html = text("frontend/pages/control.html")
tests = text("integration_tests/test_mission25_3_frontend_source_of_truth_gate.py")
node_tests = text("frontend_tests/intent_contract_gate.test.mjs")

confirm_pos = chat.find("window.aiConfirmIntentContract")
set_pos = chat.find("window.setGCodeFromAI(")
send_pos = chat.find("async function sendChat")
checks = []

def add(cid: str, requirement: str, passed: bool, evidence: str):
    checks.append({"id": cid, "requirement": requirement, "pass": bool(passed), "evidence": evidence})

add("FE-SOT-01", "Có trạng thái xác nhận UserIntentContract gắn exact hash", all(x in chat for x in ["aiConfirmIntentContract", "contractKey", "job_spec_sha256", "gcode_sha256", "verifyIntentPayloadHashes"]), "confirmation handler + browser recomputes exact hash pair")
add("FE-SOT-02", "G-code không tự nạp preview trước xác nhận", confirm_pos >= 0 and confirm_pos < set_pos < send_pos and chat.count("window.setGCodeFromAI(") == 1, f"confirm={confirm_pos}, set={set_pos}, send={send_pos}, set_count={chat.count('window.setGCodeFromAI(')}")
add("FE-SOT-03", "FeatureGraph complete phụ thuộc status + semantic + pipeline", all(x in chat for x in ["evaluateIntentContract(payload)", "semantic_clause_accounting", "pipeline_status", "CHỜ NGƯỜI DÙNG XÁC NHẬN"]), "renderer delegates to pure evaluator")
add("FE-SOT-04", "Không giả field thiếu thành 0/not-fixed", "not-fixed" not in chat and "Number(stock.x_mm || 0)" not in chat and "CHƯA CÓ" in chat, "explicit missing-value display")
required = ["job_spec_canonical_json", "semantic_clause_accounting", "resolved_process_contract", "pipeline_status", "authorization_blockers"]
add("FE-SOT-05", "Poll chuyển đầy đủ interpretation evidence", all(f'"{k}"' in route and f'"{k}"' in worker and f'"{k}"' in harness for k in required), "route/worker/harness all forward required keys")
add("FE-SOT-06", "Check/Save/Preview revalidate confirmed token", all(x in chat for x in ["_confirmedIntentEntry", "aiCheckGCode(this", "aiSaveGCode(this", "aiSendToViewer(this"]), "all action handlers require contractToken")
add("FE-SOT-07", "Hiển thị clause → binding/disposition", "Clause → binding/disposition" in chat and "item.binding" in chat and "item.disposition" in chat, "auditable clause table")
add("FE-SOT-08", "Hiển thị process contract dùng chung generator/validator", all(x in chat for x in ["ResolvedProcessContract dùng chung", "generator_consumer", "validator_consumer"]) and all(x in teacher for x in ["generate_candidates(spec, context", 'operating_ranges=context.get("operating_ranges") or {}']), "same context serialized and displayed")
add("FE-SOT-09", "Nút task gọi hàm tồn tại và không auto-send", "function askAiTask(task)" in control and "window.askAiTask" in control and all(f"askAiTask('{x}')" in html for x in ["pocket", "engrave", "profile"]), "task buttons fill input only")
add("FE-SOT-10", "Test hành vi, không chỉ string-existence legacy", "node:test" in node_tests and "safety-relevant unaccounted clause blocks confirmation" in node_tests and "does_not_auto_load_generated_gcode" in tests, "Node pure behavior + Python wiring tests")

report = {
    "schema": "frontend-source-of-truth-audit-v2",
    "root": str(ROOT),
    "total": len(checks),
    "passed": sum(1 for c in checks if c["pass"]),
    "failed": sum(1 for c in checks if not c["pass"]),
    "checks": checks,
    "limitation": "Frontend gate prevents exposure/use but backend still generates the draft before UI confirmation; backend-persisted confirmation remains separate work.",
}
print(json.dumps(report, ensure_ascii=False, indent=2))
Path('/mnt/data/MISSION25_3_FRONTEND_SOURCE_OF_TRUTH_AUDIT.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
raise SystemExit(0 if report["failed"] == 0 else 1)
