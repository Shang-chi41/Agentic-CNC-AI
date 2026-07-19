#!/usr/bin/env python3
"""Audit closed-enum SFT JSONL and optionally verify every row against raw trajectories."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from edge_backend.ai.clarification_learning import (
    build_sft_record,
    trajectory_fingerprint_valid,
)

REQUIRED_RULES = {
    "closed_enum_only",
    "abstain_when_unclear",
    "numbers_forbidden",
    "coordinates_forbidden",
    "tool_ids_forbidden",
    "machine_authority_forbidden",
}


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


def _read_jsonl(path: Path) -> Iterable[Any]:
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc


def _approved_source_records(path: Path) -> tuple[dict[str, dict[str, Any]], int, int]:
    approved: dict[str, dict[str, Any]] = {}
    total = 0
    rejected = 0
    for value in _read_jsonl(path):
        for trajectory in _iter_trajectories(value):
            total += 1
            # Training provenance must be sealed. Unsealed historical objects may
            # still be inspected offline, but they cannot authorize a dataset row.
            if not trajectory_fingerprint_valid(trajectory):
                rejected += 1
                continue
            record = build_sft_record(trajectory)
            if record is None:
                rejected += 1
                continue
            source_hash = str(record.get("source_trajectory_sha256") or "")
            approved[source_hash] = record
    return approved, total, rejected


def audit(path: Path, trajectory_path: Path | None = None) -> dict[str, Any]:
    total = 0
    valid = 0
    invalid: list[dict[str, Any]] = []
    fingerprints: set[str] = set()
    duplicate_count = 0

    source_verification = trajectory_path is not None
    approved_sources: dict[str, dict[str, Any]] = {}
    source_total = 0
    source_rejected = 0
    if trajectory_path is not None:
        approved_sources, source_total, source_rejected = _approved_source_records(trajectory_path)

    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        total += 1
        reasons: list[str] = []
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            invalid.append({"line": line_no, "reasons": ["invalid_json"]})
            continue
        if not isinstance(row, dict) or row.get("schema") != "clarification-sft-record-v2":
            reasons.append("wrong_schema")
        inp = row.get("input") if isinstance(row, dict) else None
        out = row.get("output") if isinstance(row, dict) else None
        if not isinstance(inp, dict) or not isinstance(out, dict):
            reasons.append("missing_input_or_output")
        else:
            fields = [str(v) for v in inp.get("allowed_fields") or []]
            values = inp.get("allowed_values") or {}
            rules = inp.get("rules") or {}
            if not fields or not isinstance(values, dict):
                reasons.append("missing_closed_enum_contract")
            if any(field not in values or not isinstance(values.get(field), list) or not values.get(field) for field in fields):
                reasons.append("allowed_values_incomplete")
            if not REQUIRED_RULES.issubset({k for k, v in rules.items() if v is True}):
                reasons.append("safety_rules_incomplete")
            answers = out.get("answers")
            if not isinstance(answers, list) or not answers:
                reasons.append("missing_answers")
            else:
                seen: set[str] = set()
                for answer in answers:
                    if not isinstance(answer, dict):
                        reasons.append("answer_not_object")
                        continue
                    field = str(answer.get("field_key") or "")
                    value = str(answer.get("value") or "")
                    if field not in fields:
                        reasons.append("output_field_not_allowed")
                    if value not in {str(v) for v in values.get(field, [])}:
                        reasons.append("output_value_not_allowed")
                    if field in seen:
                        reasons.append("duplicate_output_field")
                    seen.add(field)
        source_hash = str(row.get("source_trajectory_sha256") or "") if isinstance(row, dict) else ""
        if len(source_hash) != 64 or any(ch not in "0123456789abcdef" for ch in source_hash.lower()):
            reasons.append("invalid_source_trajectory_sha256")
        if source_verification:
            expected = approved_sources.get(source_hash)
            if expected is None:
                reasons.append("source_trajectory_not_found_or_not_eligible")
            elif row != expected:
                reasons.append("record_mismatch_with_source_trajectory")
        canonical = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) if isinstance(row, dict) else line
        fp = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if fp in fingerprints:
            duplicate_count += 1
            reasons.append("duplicate_record")
        fingerprints.add(fp)
        if reasons:
            invalid.append({"line": line_no, "reasons": sorted(set(reasons))})
        else:
            valid += 1

    passed = total > 0 and not invalid
    return {
        "schema": "clarification-sft-audit-v2",
        "total": total,
        "valid": valid,
        "invalid": len(invalid),
        "duplicate_count": duplicate_count,
        "issues": invalid,
        "source_verification_performed": source_verification,
        "approved_source_trajectories": len(approved_sources),
        "source_trajectories_total": source_total,
        "source_trajectories_rejected": source_rejected,
        "passed": passed,
        "passed_for_training": passed and source_verification,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--trajectories", type=Path, help="Sealed raw trajectory JSONL used to verify provenance")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(args.dataset, args.trajectories)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["passed_for_training"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
