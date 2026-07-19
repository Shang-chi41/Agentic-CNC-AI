"""Unified System/Runtime status contract for Mission 05B."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter

from cloud_backend.middleware.auth import CurrentUser
from cloud_backend.services.mongo_service import doc_to_dict, get_col, ping as mongo_ping

router = APIRouter()

_COL_RUNTIME = "Runtime_Status"
_STALE_RUNTIME_S = int(os.getenv("SYSTEM_RUNTIME_STALE_S", "15"))


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _age_s(doc: dict | None, *fields: str) -> float | None:
    if not doc:
        return None
    now = _now_utc()
    for field in fields:
        raw = doc.get(field)
        if not raw:
            continue
        try:
            ts = raw if isinstance(raw, datetime) else datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            return (now - ts.astimezone(timezone.utc)).total_seconds()
        except Exception:
            continue
    return None


def _result(connected: bool, *, age: float | None = None, source: str = "", extra: dict | None = None) -> dict:
    status = "online" if connected else ("no_data" if age is None else "offline")
    out = {"connected": bool(connected), "status": status, "age_s": None if age is None else round(age, 1), "source": source}
    if extra:
        out.update(extra)
    return out


def _latest_runtime(entrypoint: str) -> tuple[dict | None, float | None, bool]:
    doc = get_col(_COL_RUNTIME).find_one({"entrypoint": entrypoint}, sort=[("timestamp", -1)])
    doc = doc_to_dict(doc) if doc else None
    age = _age_s(doc, "timestamp", "synced_at")
    fresh = age is not None and age <= _STALE_RUNTIME_S
    return doc, age, fresh


def _svc(doc: dict | None, key: str) -> dict:
    if not doc:
        return {}
    conn = doc.get("connection") or {}
    value = conn.get(key) or {}
    return value if isinstance(value, dict) else {}


def _svc_connected(doc: dict | None, key: str, fresh: bool) -> bool:
    return bool(fresh and _svc(doc, key).get("connected"))


def build_system_status() -> dict[str, Any]:
    main_doc, main_age, main_fresh = _latest_runtime("main")
    sim_doc, sim_age, sim_fresh = _latest_runtime("main_sim_only")

    # Active runtime is the freshest live entrypoint. If both are fresh, report
    # both so the operator sees a possible operator/config conflict.
    live = []
    if main_fresh:
        live.append("main")
    if sim_fresh:
        live.append("main_sim_only")
    if len(live) == 1:
        active_entrypoint = live[0]
    elif len(live) > 1:
        active_entrypoint = "multiple"
    else:
        active_entrypoint = "none"

    nx_main = _svc_connected(main_doc, "nxmcd", main_fresh)
    nx_sim = _svc_connected(sim_doc, "nxmcd", sim_fresh)
    nx_source_doc = main_doc if nx_main else sim_doc
    nx_age = main_age if nx_main else sim_age

    connection = {
        "fluidnc": _result(
            _svc_connected(main_doc, "fluidnc", main_fresh),
            age=main_age,
            source="main.fluidnc_telnet_socket",
            extra=_svc(main_doc, "fluidnc"),
        ),
        "matlab_main": _result(
            _svc_connected(main_doc, "matlab_main", main_fresh),
            age=main_age,
            source="main.matlab_sender_socket",
            extra=_svc(main_doc, "matlab_main"),
        ),
        "sim_test": _result(
            _svc_connected(sim_doc, "sim_test", sim_fresh),
            age=sim_age,
            source="main_sim_only.runtime_heartbeat",
            extra=_svc(sim_doc, "sim_test"),
        ),
        "nxmcd": _result(
            bool(nx_main or nx_sim),
            age=nx_age,
            source="nxmcd_tcp_client",
            extra=_svc(nx_source_doc, "nxmcd"),
        ),
        "mongodb": _result(mongo_ping(), source="cloud_mongo_ping"),
    }

    dataflow_doc = main_doc if main_fresh else (sim_doc if sim_fresh else None)
    dataflow = (dataflow_doc or {}).get("dataflow") or {"mode": "offline", "source_of_truth": "none", "drives_nx_mcd": False}
    gate = (main_doc or {}).get("gate") or {
        "machine_run_allowed": False,
        "reason": "main.py runtime heartbeat is not fresh",
    }

    return {
        "timestamp": _now_utc().isoformat(),
        "runtime": {
            "active_entrypoint": active_entrypoint,
            "live_entrypoints": live,
            "stale_after_s": _STALE_RUNTIME_S,
            "main": {"fresh": main_fresh, "age_s": None if main_age is None else round(main_age, 1), "env": (main_doc or {}).get("env", {})},
            "main_sim_only": {"fresh": sim_fresh, "age_s": None if sim_age is None else round(sim_age, 1), "env": (sim_doc or {}).get("env", {})},
        },
        "connection": connection,
        "dataflow": dataflow,
        "gate": gate,
    }


@router.get("/status", summary="Unified runtime / connection / dataflow / gate status")
def system_status(user: CurrentUser) -> dict[str, Any]:
    return build_system_status()
