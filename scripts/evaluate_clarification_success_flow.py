#!/usr/bin/env python3
"""Fit the success-only transition guard and score candidate trajectories."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from edge_backend.ai.success_flow_guard import SuccessFlowModel


def _load(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
            if isinstance(value, dict):
                nested = value.get("clarification_trajectory")
                if isinstance(nested, dict):
                    rows.append(nested)
                elif isinstance(nested, list):
                    rows.extend(item for item in nested if isinstance(item, dict))
                else:
                    rows.append(value)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("success_jsonl", type=Path)
    parser.add_argument("candidate_jsonl", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    success = _load(args.success_jsonl)
    candidates = _load(args.candidate_jsonl)
    model = SuccessFlowModel().fit(success)
    result = {
        "schema": "success-flow-evaluation-v1",
        "model": {
            "fitted_trajectories": model.fitted_trajectories,
            "allowed_transitions": sorted([list(item) for item in model.allowed_transitions]),
            "terminal_stages": sorted(model.terminal_stages),
        },
        "scores": [model.score(item) for item in candidates],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "fitted": model.fitted_trajectories,
        "candidates": len(candidates),
        "anomalous": sum(1 for item in result["scores"] if item["anomaly_count"]),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
