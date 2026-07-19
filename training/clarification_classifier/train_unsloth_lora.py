#!/usr/bin/env python3
"""Optional offline LoRA SFT recipe for the closed-enum clarification classifier.

This file is deliberately isolated from runtime. It does not publish, load, or
promote the resulting adapter. Promotion requires independent holdout and safety
evaluation defined in the mission gates.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit_clarification_training_data import audit


def load_rows(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value: Any = json.loads(line)
            if not isinstance(value, dict) or value.get("schema") != "clarification-sft-record-v2":
                raise ValueError(f"{path}:{line_no}: not a clarification SFT record")
            prompt = json.dumps(value["input"], ensure_ascii=False, sort_keys=True)
            answer = json.dumps(value["output"], ensure_ascii=False, sort_keys=True)
            rows.append({"text": f"<|user|>\n{prompt}\n<|assistant|>\n{answer}"})
    if not rows:
        raise ValueError("dataset contains no oracle-approved records")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--trajectories", required=True, type=Path)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-seq-length", type=int, default=1024)
    parser.add_argument("--epochs", type=float, default=1.0)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--gradient-accumulation", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    args = parser.parse_args()

    audit_report = audit(args.dataset, args.trajectories)
    if audit_report.get("passed_for_training") is not True:
        raise SystemExit(
            "Dataset failed source-linked clarification audit; training is blocked."
        )
    rows = load_rows(args.dataset)

    try:
        from datasets import Dataset
        from transformers import TrainingArguments
        from trl import SFTTrainer
        from unsloth import FastLanguageModel
    except ImportError as exc:
        raise SystemExit(
            "Optional training dependencies are unavailable. Install Unsloth, "
            "datasets, transformers and trl in a separate training environment."
        ) from exc

    dataset = Dataset.from_list(rows)
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.model,
        max_seq_length=args.max_seq_length,
        dtype=None,
        load_in_4bit=True,
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=16,
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        lora_alpha=16,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=3407,
    )
    args.output.mkdir(parents=True, exist_ok=True)
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=args.max_seq_length,
        args=TrainingArguments(
            output_dir=str(args.output / "checkpoints"),
            per_device_train_batch_size=args.batch_size,
            gradient_accumulation_steps=args.gradient_accumulation,
            num_train_epochs=args.epochs,
            learning_rate=args.learning_rate,
            logging_steps=1,
            save_strategy="epoch",
            report_to="none",
            seed=3407,
        ),
    )
    trainer.train()
    model.save_pretrained(str(args.output / "adapter"))
    tokenizer.save_pretrained(str(args.output / "adapter"))
    (args.output / "TRAINING_NOT_PROMOTED.json").write_text(
        json.dumps({
            "schema": "clarification-training-output-v1",
            "status": "TRAINED_NOT_PROMOTED",
            "records": len(rows),
            "model": args.model,
            "requires": ["hidden_holdout", "safety_regression", "shadow_deployment", "manual_promotion"],
        }, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
