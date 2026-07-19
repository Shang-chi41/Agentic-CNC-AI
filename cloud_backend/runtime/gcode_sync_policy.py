"""Merge policy for Edge -> Cloud G-code synchronization.

Cloud owns operator confirmation/run authorization.  Edge owns CHECK/runtime
observations.  A stale Edge snapshot of the *same immutable artifact* must not
roll Cloud back from confirmed/queued/executing to approved/needs_check.
A genuinely changed artifact invalidates prior confirmation and run authority.
"""

from __future__ import annotations

from typing import Any


_CLOUD_AUTHORITY_FIELDS = (
    "machine_run_confirmed",
    "confirmed_from_status",
    "confirmed_artifact_hash",
    "confirmed_check_id",
    "confirmed_sync_epoch_id",
    "confirmed_context_fingerprint",
    "confirmed_by",
    "confirmed_at",
    "machine_run_authorized",
    "machine_run_authorization",
    "queued_at",
    "execution_command_id",
)

_STATUS_RANK = {
    "needs_check": 10,
    "pending_validation": 10,
    "pending_confirmation": 15,
    "approved": 20,
    "confirmed": 30,
    "queued": 40,
    "processing": 45,
    "executing": 50,
    "executed": 60,
}
_TERMINAL_FAILURES = {"rejected", "blocked", "failed"}


def _artifact_identity(doc: dict[str, Any] | None) -> str:
    if not doc:
        return ""
    return str(
        doc.get("artifact_hash")
        or doc.get("approved_checksum")
        or doc.get("checksum")
        or ""
    ).strip().lower()


def merge_edge_gcode_record(
    existing: dict[str, Any] | None,
    incoming: dict[str, Any],
    *,
    synced_at: str,
) -> dict[str, Any]:
    """Return the fields Cloud may safely ``$set`` for one Edge record."""
    current = dict(existing or {})
    merged = dict(incoming)
    merged["synced_at"] = synced_at

    if not current:
        return merged

    existing_confirmed_hash = str(current.get("confirmed_artifact_hash") or "").strip().lower()
    incoming_identity = _artifact_identity(incoming)
    same_confirmed_artifact = bool(
        existing_confirmed_hash
        and incoming_identity
        and existing_confirmed_hash == incoming_identity
    )

    if same_confirmed_artifact:
        # Preserve explicit human/run authority against an older Edge snapshot.
        for field in _CLOUD_AUTHORITY_FIELDS:
            if field in current:
                merged[field] = current[field]

        old_status = str(current.get("status") or "").lower()
        new_status = str(incoming.get("status") or "").lower()
        if new_status in _TERMINAL_FAILURES:
            # A terminal failure must never leave a stale live run grant behind.
            # Confirmation metadata is retained for audit, but status != confirmed
            # and run authorization is explicitly revoked before any future retry.
            merged["machine_run_authorized"] = False
            merged["machine_run_authorization"] = None
            merged["run_authorization_invalidated_reason"] = (
                f"Edge reported terminal G-code status '{new_status}'"
            )
            merged["run_authorization_invalidated_at"] = synced_at
        elif (
            old_status
            and new_status
            and _STATUS_RANK.get(new_status, -1) < _STATUS_RANK.get(old_status, -1)
        ):
            merged["status"] = current.get("status")
        return merged

    # A different immutable artifact invalidates any prior operator/run grant.
    if (
        current.get("machine_run_confirmed")
        or current.get("machine_run_authorized")
        or current.get("confirmed_artifact_hash")
        or str(current.get("status") or "").lower() in {"confirmed", "queued", "processing", "executing"}
    ):
        merged.update({
            "machine_run_confirmed": False,
            "machine_run_authorized": False,
            "machine_run_authorization": None,
            "confirmed_from_status": None,
            "confirmed_artifact_hash": None,
            "confirmed_check_id": None,
            "confirmed_sync_epoch_id": None,
            "confirmed_context_fingerprint": None,
            "confirmed_by": None,
            "confirmed_at": None,
            "queued_at": None,
            "execution_command_id": None,
            "confirmation_invalidated_reason": "Edge sync reported a different immutable G-code artifact",
            "confirmation_invalidated_at": synced_at,
        })

    return merged
