"""Unified System/Runtime status contract for Mission 05B."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter

from cloud_backend.middleware.auth import CurrentUser
from cloud_backend.services.mongo_service import doc_to_dict, get_col, ping as mongo_ping
from cloud_backend.services.workflow_contract import empty_workflow_state
from cloud_backend.services.system_contract import derive_edge_runtime_connection

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
        # Preserve canonical connected/status/age/source computed by Cloud.
        detail = {k: v for k, v in extra.items() if k not in {"connected", "status", "age_s", "source"}}
        out.update(detail)
        if extra.get("source"):
            out["detail_source"] = extra.get("source")
    return out


def _svc_age(doc: dict | None, key: str, fallback_age: float | None) -> float | None:
    value = _svc(doc, key)
    age = _age_s(value, "last_seen_at", "last_connected_at", "latest_timestamp", "timestamp")
    return age if age is not None else fallback_age


def _svc_result(doc: dict | None, key: str, fresh: bool, fallback_age: float | None, source: str) -> dict:
    value = _svc(doc, key)
    connected = bool(fresh and value.get("connected"))
    # If the service reports disconnected and has never been seen, keep no_data.
    age = _svc_age(doc, key, fallback_age if value else None)
    return _result(connected, age=age, source=source, extra=value)


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

    matlab_main_live = _svc_connected(main_doc, "matlab_main", main_fresh)
    matlab_sim_live = _svc_connected(sim_doc, "matlab_main", sim_fresh)
    matlab_source_doc = main_doc if matlab_main_live else sim_doc
    matlab_age = main_age if matlab_main_live else sim_age

    nx_main = _svc_connected(main_doc, "nxmcd", main_fresh)
    nx_sim = _svc_connected(sim_doc, "nxmcd", sim_fresh)
    nx_source_doc = main_doc if nx_main else sim_doc
    nx_age = main_age if nx_main else sim_age

    # CONNECTION is service/device liveness only; machine gate and motion logs are separate.
    matlab_docs = []
    if main_fresh and _svc(main_doc, "matlab_main").get("connected"):
        matlab_docs.append((main_doc, main_age, _svc_age(main_doc, "matlab_main", main_age)))
    if sim_fresh and _svc(sim_doc, "matlab_main").get("connected"):
        matlab_docs.append((sim_doc, sim_age, _svc_age(sim_doc, "matlab_main", sim_age)))
    matlab_docs.sort(key=lambda item: item[2] if item[2] is not None else 1e18)
    matlab_doc = matlab_docs[0][0] if matlab_docs else (main_doc if main_doc else sim_doc)
    matlab_age = matlab_docs[0][2] if matlab_docs else None

    nx_docs = []
    if main_fresh and _svc(main_doc, "nxmcd").get("connected"):
        nx_docs.append((main_doc, main_age, _svc_age(main_doc, "nxmcd", main_age)))
    if sim_fresh and _svc(sim_doc, "nxmcd").get("connected"):
        nx_docs.append((sim_doc, sim_age, _svc_age(sim_doc, "nxmcd", sim_age)))
    nx_docs.sort(key=lambda item: item[2] if item[2] is not None else 1e18)
    nx_doc = nx_docs[0][0] if nx_docs else (main_doc if main_doc else sim_doc)
    nx_age = nx_docs[0][2] if nx_docs else None

    edge_runtime = derive_edge_runtime_connection(
        active_entrypoint=active_entrypoint,
        live_entrypoints=live,
        main_age_s=main_age,
        sim_age_s=sim_age,
    )

    connection = {
        "edge_runtime": edge_runtime,
        "fluidnc": _svc_result(main_doc, "fluidnc", main_fresh, main_age, "main.fluidnc_telnet_socket"),
        "matlab_main": _result(
            bool(matlab_docs),
            age=matlab_age,
            source="matlab_bridge_connection",
            extra=_svc(matlab_doc, "matlab_main"),
        ),
        "sim_test": _svc_result(sim_doc, "sim_test", sim_fresh, sim_age, "main_sim_only.runtime_heartbeat"),
        "nxmcd": _result(
            bool(nx_docs),
            age=nx_age,
            source="nxmcd_tcp_client_socket",
            extra=_svc(nx_doc, "nxmcd"),
        ),
        "mongodb": _result(mongo_ping(), source="cloud_mongo_ping"),
    }

    dataflow_doc = main_doc if main_fresh else (sim_doc if sim_fresh else None)
    dataflow = (dataflow_doc or {}).get("dataflow") or {"mode": "offline", "source_of_truth": "none", "drives_nx_mcd": False}
    gate = dict((main_doc or {}).get("gate") or {
        "machine_run_allowed": False,
        "reason": "main.py runtime heartbeat is not fresh",
    })
    if active_entrypoint == "multiple":
        gate["machine_run_allowed"] = False
        gate["reason"] = "main.py và main_sim_only cùng active; production actions bị khóa"
        gate["reasons"] = [gate["reason"]]

    workflow_doc = main_doc if main_fresh else (sim_doc if sim_fresh else None)
    workflow_state = (workflow_doc or {}).get("workflow_state") or empty_workflow_state()

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
        "workflow_state": workflow_state,
        "gate": gate,
    }


@router.get("/status", summary="Unified runtime / connection / dataflow / gate status")
def system_status(user: CurrentUser) -> dict[str, Any]:
    return build_system_status()


@router.get("/workflow", summary="Canonical six-dimensional workflow state")
def workflow_status(user: CurrentUser) -> dict[str, Any]:
    status = build_system_status()
    return {
        "timestamp": status["timestamp"],
        "runtime": status["runtime"],
        "workflow_state": status["workflow_state"],
        "gate": status["gate"],
    }
