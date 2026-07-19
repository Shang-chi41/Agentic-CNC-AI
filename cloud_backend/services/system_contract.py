"""Pure canonical system-status helpers with no FastAPI/Mongo imports."""
from __future__ import annotations

from typing import Iterable


def derive_edge_runtime_connection(
    *,
    active_entrypoint: str,
    live_entrypoints: Iterable[str],
    main_age_s: float | None,
    sim_age_s: float | None,
) -> dict:
    live = list(live_entrypoints)
    ages = [float(age) for age in (main_age_s, sim_age_s) if age is not None]
    age = min(ages) if ages else None
    age_value = None if age is None else round(age, 1)
    if active_entrypoint == "multiple":
        return {
            "connected": False,
            "status": "conflict",
            "age_s": age_value,
            "source": "edge_runtime_heartbeat",
            "active_entrypoint": active_entrypoint,
            "live_entrypoints": live,
            "reason": "main.py và main_sim_only cùng active",
        }
    connected = active_entrypoint in {"main", "main_sim_only"}
    return {
        "connected": connected,
        "status": "online" if connected else ("no_data" if age is None else "offline"),
        "age_s": age_value,
        "source": "edge_runtime_heartbeat",
        "active_entrypoint": active_entrypoint,
        "live_entrypoints": live,
    }
