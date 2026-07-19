# Clarification classifier training boundary

This directory is **offline training only**. Nothing here is imported by CNC runtime.

## Purpose

Train an adapter that maps a free-form answer to one value from a caller-provided closed enum. It must never learn to generate numeric dimensions, coordinates, tool IDs, G-code, CHECK/RUN authorization, or arbitrary operations.

## Required data path

1. Runtime emits `clarification-trajectory-v1` records.
2. `clarification-success-oracle-v3` separates runtime success from classifier-training eligibility and rejects dirty deterministic facts, provider garbage, unbound fields, contradictions, repeated questions, or machine authority.
3. `scripts/export_clarification_training_data.py` exports only eligible records.
4. Training uses the exported JSONL.
5. A separate holdout evaluator compares the adapter against the current baseline.
6. Promotion is manual and starts in shadow mode. Runtime does not auto-load a newly trained adapter.

## Example

```bash
python scripts/export_clarification_training_data.py \
  data/clarification_trajectories.jsonl \
  training/clarification_classifier/sft_success.jsonl \
  --summary training/clarification_classifier/export_summary.json

python training/clarification_classifier/train_unsloth_lora.py \
  --dataset training/clarification_classifier/sft_success.jsonl \
  --model unsloth/Qwen3-4B-unsloth-bnb-4bit \
  --output training/clarification_classifier/output_adapter
```

The Unsloth script is an optional recipe. It exits clearly when optional packages or a supported accelerator are unavailable.
