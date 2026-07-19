#!/usr/bin/env python3
"""Export only success-oracle-approved clarification trajectories to SFT JSONL.

Input accepts either:
- one clarification trajectory object per JSONL line; or
- an envelope containing ``clarification_trajectory``; or
- a conversation-state object containing a ``clarification_trajectory`` list.

The exporter is offline-only. It never modifies runtime state, model weights, or
machine authorization.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from edge_backend.ai.clarification_learning import build_sft_record


def _iter_trajectories(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, list):
        for item in value:
            yield from _iter_trajectories(item)
        return
    if not isinstance(value, dict):
        return
    nested = value.get("clarification_trajectory")
    if isinstance(nested, list):
        for item in nested:
            if isinstance(item, dict):
                yield item
        return
    if isinstance(nested, dict):
        yield nested
        return
    if value.get("schema") == "clarification-trajectory-v1" or "classification" in value:
        yield value


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            text = line.strip()
            if not text:
                continue
            try:
                value = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
            yield from _iter_trajectories(value)


def export(input_path: Path, output_path: Path) -> dict[str, int]:
    total = 0
    exported = 0
    rejected = 0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as out:
        for trajectory in _read_jsonl(input_path):
            total += 1
            record = build_sft_record(trajectory)
            if record is None:
                rejected += 1
                continue
            out.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            exported += 1
    return {"total": total, "exported": exported, "rejected": rejected}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Trajectory JSONL file")
    parser.add_argument("output", type=Path, help="Success-only SFT JSONL file")
    parser.add_argument("--summary", type=Path, help="Optional summary JSON path")
    args = parser.parse_args()
    summary = export(args.input, args.output)
    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
