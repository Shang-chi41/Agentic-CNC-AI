"""Deterministic recovery policy for Cloud -> Edge machine commands.

A lost ACK is not proof that a physical side effect did not happen.  Only
commands that are safe to repeat may be returned to ``pending`` automatically.
Everything else requires reconciliation instead of blind retry.
"""

from __future__ import annotations


_RETRY_SAFE_ACTIONS = frozenset({"estop", "stop"})


def stale_command_recovery_policy(action: str) -> str:
    normalized = str(action or "").strip().lower()
    if normalized == "run_gcode":
        return "run_guard"
    if normalized in _RETRY_SAFE_ACTIONS:
        return "retry_safe"
    return "reconciliation_required"


def may_retry_uncertain_processing(action: str) -> bool:
    return stale_command_recovery_policy(action) == "retry_safe"
