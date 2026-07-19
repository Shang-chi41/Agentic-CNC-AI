from __future__ import annotations
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NODE_TEST = ["node", "--experimental-default-type=module", "--test", "frontend_tests/intent_contract_gate.test.mjs"]
PY_TEST = ["python", "-m", "pytest", "-q", "integration_tests/test_mission25_3_frontend_source_of_truth_gate.py"]

mutants = [
    {
        "id": "M-FE-01-AUTO-PREVIEW",
        "path": "frontend/js/ai_chat.js",
        "old": "if (payload?.has_gcode && payload?.gcode) {\n            const note = evaluation.confirmable",
        "new": "if (payload?.has_gcode && payload?.gcode) {\n            if (typeof window.setGCodeFromAI === 'function') window.setGCodeFromAI(payload.gcode);\n            const note = evaluation.confirmable",
        "cmd": PY_TEST,
    },
    {
        "id": "M-FE-02-IGNORE-UNACCOUNTED",
        "path": "frontend/js/intent_contract_gate.js",
        "old": "if (safetyRelevant) return disposition !== 'BOUND';",
        "new": "if (safetyRelevant) return false;",
        "cmd": NODE_TEST,
    },
    {
        "id": "M-FE-03-BYPASS-GCODE-HASH",
        "path": "frontend/js/intent_contract_gate.js",
        "old": "const gcodeHashMatches = gcodeDigest === String(payload.gcode_sha256 || '').toLowerCase();",
        "new": "const gcodeHashMatches = true;",
        "cmd": NODE_TEST,
    },
    {
        "id": "M-FE-04-BYPASS-CONFIRM-TOKEN",
        "path": "frontend/js/ai_chat.js",
        "old": "if (!entry || entry.confirmed !== true) return null;",
        "new": "if (!entry) return null;",
        "cmd": PY_TEST,
    },
    {
        "id": "M-FE-06-BYPASS-ACTION-ELIGIBILITY",
        "path": "frontend/js/ai_chat.js",
        "old": "if (current.actionEligible && typeof window.setGCodeFromAI === 'function') {",
        "new": "if (typeof window.setGCodeFromAI === 'function') {",
        "cmd": PY_TEST,
    },
    {
        "id": "M-FE-05-DROP-CANONICAL-POLL",
        "path": "cloud_backend/routes/ai_routes.py",
        "old": '"job_spec_sha256", "job_spec_canonical_json", "semantic_clause_accounting",',
        "new": '"job_spec_sha256", "semantic_clause_accounting",',
        "cmd": PY_TEST,
    },
]

results = []
for mutant in mutants:
    path = ROOT / mutant["path"]
    original = path.read_text(encoding="utf-8")
    if mutant["old"] not in original:
        results.append({"id": mutant["id"], "status": "HARNESS_ERROR", "reason": "mutation target missing"})
        continue
    try:
        path.write_text(original.replace(mutant["old"], mutant["new"], 1), encoding="utf-8")
        proc = subprocess.run(mutant["cmd"], cwd=ROOT, text=True, capture_output=True, timeout=45)
        killed = proc.returncode != 0
        results.append({
            "id": mutant["id"],
            "status": "KILLED" if killed else "SURVIVED",
            "returncode": proc.returncode,
            "stdout_tail": proc.stdout[-1800:],
            "stderr_tail": proc.stderr[-1000:],
        })
    except subprocess.TimeoutExpired as exc:
        results.append({"id": mutant["id"], "status": "TIMEOUT", "stdout_tail": str(exc.stdout or '')[-1000:]})
    finally:
        path.write_text(original, encoding="utf-8")

report = {
    "schema": "mission25.3-frontend-gate-mutation-v1",
    "total": len(results),
    "killed": sum(r["status"] == "KILLED" for r in results),
    "survived": sum(r["status"] == "SURVIVED" for r in results),
    "timeouts": sum(r["status"] == "TIMEOUT" for r in results),
    "harness_errors": sum(r["status"] == "HARNESS_ERROR" for r in results),
    "results": results,
}
output = Path('/mnt/data/MISSION25_3_FRONTEND_GATE_MUTATION_REPORT.json')
output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(0 if report["killed"] == len(results) else 1)
