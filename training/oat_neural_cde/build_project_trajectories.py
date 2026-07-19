#!/usr/bin/env python3
"""Build sealed success trajectories and labelled fault-injected failures.

All success trajectories are produced by the project's real contextual runtime.
Failure labels are used only for evaluation; the Neural-CDE trainer reads success
trajectories exclusively during fitting.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import random
import sys
import unicodedata
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from edge_backend.ai.contextual_action_conversation import ConversationState, execute_contextual_turn
from edge_backend.ai.clarification_learning import evaluate_clarification_trajectory, trajectory_fingerprint


def _spec(kind: str = "rectangular") -> dict[str, Any]:
    feature: dict[str, Any] = {
        "id": "F1",
        "type": "rectangular_contour" if kind == "rectangular" else "circular_feature",
        "operation": "",
        "x_bounds": [-5, 5],
        "y_bounds": [-10, 10],
        "depth_mm": 8,
    }
    if kind == "circular":
        feature["diameter_mm"] = 18
    return {
        "stock": {"x_mm": 36, "y_mm": 36, "z_mm": 30, "material": "Aluminum"},
        "tool": {"tool_id": "", "family": "END_MILL", "diameter_mm": 6},
        "safe_z_mm": 3,
        "features": [feature],
    }


def _state(field: str, question: str, kind: str = "rectangular", thread: str = "oat") -> ConversationState:
    return ConversationState(
        thread_id=thread,
        active_job_spec=_spec(kind),
        unresolved_requirements=[field],
        pending_action="AWAIT_USER_REQUIREMENTS",
        pending_question=question,
    )


BASE_CASES: list[dict[str, Any]] = [
    # role
    {"field": "F1.role", "question": "Bạn muốn giữ hay khoét phần chữ nhật?", "message": "Giữ nguyên phần giữa và cho dao chạy vòng ngoài", "value": "RECTANGULAR_CONTOUR_OUTSIDE"},
    {"field": "F1.role", "question": "Bạn muốn giữ hay khoét phần chữ nhật?", "message": "Chừa miếng ở tâm lại dao đi bên ngoài mép", "value": "RECTANGULAR_CONTOUR_OUTSIDE"},
    {"field": "F1.role", "question": "Bạn muốn giữ hay khoét phần chữ nhật?", "message": "Khoét bỏ toàn bộ phần chữ nhật ở giữa", "value": "RECTANGULAR_POCKET"},
    {"field": "F1.role", "question": "Bạn muốn giữ hay khoét phần chữ nhật?", "message": "Lấy hết vật liệu bên trong hình chữ nhật", "value": "RECTANGULAR_POCKET"},
    {"field": "F1.role", "question": "Bạn muốn giữ hay khoét phần chữ nhật?", "message": "Cho dao bám phía trong đường biên", "value": "RECTANGULAR_CONTOUR_INSIDE"},
    # interaction
    {"field": "feature.interaction", "question": "Xử lý vùng giao nhau thế nào?", "message": "Giữ hai feature độc lập riêng biệt", "value": "KEEP_FEATURES_INDEPENDENT"},
    {"field": "feature.interaction", "question": "Xử lý vùng giao nhau thế nào?", "message": "Gộp vùng giao nhau thành một vùng", "value": "MERGE_OVERLAP_REGION"},
    {"field": "feature.interaction", "question": "Rãnh có được cắt qua đảo không?", "message": "Dừng rãnh trước phần đảo cần giữ", "value": "STOP_BEFORE_KEPT_FEATURE"},
    {"field": "feature.interaction", "question": "Rãnh có được cắt qua đảo không?", "message": "Cho rãnh cắt xuyên qua đảo vật liệu", "value": "ALLOW_CROSS_FEATURE_CUT"},
    # retention
    {"field": "part.retention", "question": "Giữ chi tiết bằng cách nào?", "message": "Dùng tabs làm cầu giữ chi tiết", "value": "TABS"},
    {"field": "part.retention", "question": "Giữ chi tiết bằng cách nào?", "message": "Chừa lại một lớp mỏng onion skin", "value": "ONION_SKIN"},
    {"field": "part.retention", "question": "Giữ chi tiết bằng cách nào?", "message": "Giữ bằng bàn hút chân không", "value": "VACUUM_FIXTURE"},
    {"field": "part.retention", "question": "Giữ chi tiết bằng cách nào?", "message": "Dùng keo và đồ gá hy sinh", "value": "SACRIFICIAL_HOLDING"},
    {"field": "part.retention", "question": "Giữ chi tiết bằng cách nào?", "message": "Không phay xuyên chi tiết", "value": "NOT_THROUGH"},
    # fixture
    {"field": "fixture.strategy", "question": "Bạn gá phôi bằng gì?", "message": "Tôi kẹp phôi bằng ê tô", "value": "VISE"},
    {"field": "fixture.strategy", "question": "Bạn gá phôi bằng gì?", "message": "Dùng đòn kẹp hai bên", "value": "CLAMPS"},
    {"field": "fixture.strategy", "question": "Bạn gá phôi bằng gì?", "message": "Gá bằng bàn vacuum", "value": "VACUUM_FIXTURE"},
    {"field": "fixture.strategy", "question": "Bạn gá phôi bằng gì?", "message": "Dán keo lên tấm hy sinh", "value": "SACRIFICIAL_HOLDING"},
]


def _strip_accents(text: str) -> str:
    value = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in value if unicodedata.category(ch) != "Mn").replace("đ", "d").replace("Đ", "D")


def variants(text: str) -> list[str]:
    base = text.strip()
    return [
        base,
        base.lower(),
        f"Ý tôi là {base.lower()} nhé",
        base.replace(" ", "  "),
        base + "...",
        _strip_accents(base),
        f"{base}, được không",
        base.replace(" và ", " "),
    ]


def run_success(case: dict[str, Any], message: str, index: int) -> dict[str, Any] | None:
    result = execute_contextual_turn(
        message,
        state=_state(case["field"], case["question"], thread=f"oat-success-{index}"),
    )
    trajectory = deepcopy(result.get("clarification_trajectory") or {})
    confirmed = (result.get("conversation_state") or {}).get("confirmed_user_values") or {}
    if confirmed.get(case["field"]) != case["value"]:
        return None
    oracle = evaluate_clarification_trajectory(trajectory)
    if oracle.get("eligible_success") is not True:
        return None
    trajectory["success_oracle"] = oracle
    trajectory["trajectory_sha256"] = trajectory_fingerprint(trajectory)
    trajectory["dataset_meta"] = {
        "source": "project_runtime",
        "case_field": case["field"],
        "expected_value": case["value"],
        "variant_sha256": hashlib.sha256(message.encode("utf-8")).hexdigest(),
    }
    # Re-seal because dataset_meta is part of the record.
    trajectory["trajectory_sha256"] = trajectory_fingerprint(trajectory)
    return trajectory


def mutate_success(base: dict[str, Any], kind: str, rng: random.Random) -> tuple[dict[str, Any], list[int]]:
    item = deepcopy(base)
    steps = item["steps"]

    def stage_index(stage: str) -> int:
        for idx, step in enumerate(steps):
            if str((step or {}).get("stage") or "") == stage:
                return idx
        raise RuntimeError(f"Missing expected stage {stage}: {[x.get('stage') for x in steps]}")

    # 0-based labels always refer to the serialized runtime trajectory.
    closed_enum_idx = stage_index("CLOSED_ENUM_CLASSIFY")
    semantic_bind_idx = stage_index("SEMANTIC_BIND")
    reconcile_idx = stage_index("CROSS_LAYER_RECONCILE")
    next_action_idx = stage_index("NEXT_ACTION")
    deterministic_idx = stage_index("DETERMINISTIC_EXTRACT")
    if kind == "invalid_enum":
        item["classification"]["accepted"] = {"F1.role": "INVENTED_OPERATION"}
        item["classification"]["abstained"] = False
        labels = [closed_enum_idx]
    elif kind == "provider_garbage":
        item["classification"]["rejected"] = [{"field_key": "tool.id", "reason": "field_not_allowed"}]
        labels = [closed_enum_idx]
    elif kind == "unbound":
        item["semantic_bound_fields"] = []
        steps[semantic_bind_idx]["bound_fields"] = []
        labels = [semantic_bind_idx]
    elif kind == "contradiction":
        item["contradictions"] = ["semantic_binding_mismatch:F1.role"]
        steps[reconcile_idx]["contradictions"] = list(item["contradictions"])
        labels = [reconcile_idx]
    elif kind == "repeated_question":
        accepted = list((item.get("classification") or {}).get("accepted") or {})
        field = accepted[0] if accepted else "F1.role"
        item["remaining_requirements"] = [field]
        labels = [next_action_idx]
    elif kind == "machine_authority":
        item["machine_authorized"] = True
        labels = [next_action_idx]
    elif kind == "skip_bind":
        item["steps"] = [step for idx, step in enumerate(steps) if idx != semantic_bind_idx]
        labels = [semantic_bind_idx]
    elif kind == "dirty_fact":
        item["deterministic_values"] = {"tool": "chạy vòng bên"}
        item["deterministic_validation"] = {"valid": False, "rejected": [{"field_key": "tool"}]}
        steps[deterministic_idx]["observed_fields"] = ["tool"]
        labels = [deterministic_idx]
    else:
        raise ValueError(kind)
    item.pop("trajectory_sha256", None)
    item["failure_meta"] = {"fault": kind, "error_steps": labels}
    return item, labels


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=3407)
    parser.add_argument("--min-success", type=int, default=100)
    args = parser.parse_args()
    rng = random.Random(args.seed)

    successes: list[dict[str, Any]] = []
    seen: set[str] = set()
    index = 0
    for round_id in range(3):
        for case in BASE_CASES:
            for message in variants(case["message"]):
                decorated = message if round_id == 0 else (f"{message} " + ("ạ" * round_id))
                key = f"{case['field']}|{decorated}"
                if key in seen:
                    continue
                seen.add(key)
                trajectory = run_success(case, decorated, index)
                index += 1
                if trajectory is not None:
                    successes.append(trajectory)
    if len(successes) < args.min_success:
        raise SystemExit(f"Only {len(successes)} runtime successes; need at least {args.min_success}")

    rng.shuffle(successes)
    successes = successes[: max(args.min_success, min(len(successes), 144))]
    fault_types = [
        "invalid_enum", "provider_garbage", "unbound", "contradiction",
        "repeated_question", "machine_authority", "skip_bind", "dirty_fact",
    ]
    failures: list[dict[str, Any]] = []
    for i, base in enumerate(successes[:96]):
        mutant, _ = mutate_success(base, fault_types[i % len(fault_types)], rng)
        failures.append(mutant)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.output_dir / "success_trajectories.jsonl", successes)
    write_jsonl(args.output_dir / "failure_trajectories.jsonl", failures)
    manifest = {
        "schema": "oat-project-trajectory-dataset-v1",
        "seed": args.seed,
        "success_count": len(successes),
        "failure_count": len(failures),
        "success_source": "execute_contextual_turn runtime + independent success oracle",
        "failure_source": "fault injection; labels excluded from training",
        "fault_types": fault_types,
    }
    (args.output_dir / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
