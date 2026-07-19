"""Cloud fallback shape for canonical Edge workflow state."""
from __future__ import annotations


def empty_workflow_state() -> dict:
    return {
        "workflow": "NONE",
        "session_id": None,
        "connection": {},
        "availability": {"state": "UNKNOWN", "reasons": []},
        "activity": {"state": "IDLE", "phase": "NONE", "progress": 0.0},
        "completion": {"state": "UNKNOWN"},
        "approval": {"state": "UNKNOWN", "reasons": []},
        "run_permission": {"state": "BLOCKED", "reasons": ["No fresh Edge workflow"]},
        "ui": {"color": "gray"},
    }
