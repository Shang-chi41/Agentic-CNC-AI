#!/usr/bin/env python3
"""CPU reproduction of OAT-style one-class failure attribution with Neural CDE.

This is an independent project adaptation of the published OAT method:
- fit only on successful project trajectories;
- model continuous step dynamics with a gated Neural CDE;
- use per-step reconstruction error as anomaly score;
- calibrate a conformal threshold on held-out successes;
- evaluate labelled failures only after training.

It does not claim to be the authors' official implementation and uses structured
project-state vectors instead of Qwen hidden states.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
from pathlib import Path
import random
import time
from typing import Any

import numpy as np
import torch
torch.set_num_threads(max(1, int(__import__("os").getenv("OAT_TORCH_THREADS", "1"))))
from torch import nn
import torchcde
from sklearn.metrics import average_precision_score, roc_auc_score

STAGES = [
    "DETERMINISTIC_EXTRACT",
    "METHOD_POLICY",
    "SEMANTIC_INTERPRET",
    "CLOSED_ENUM_CLASSIFY",
    "SEMANTIC_BIND",
    "CROSS_LAYER_RECONCILE",
    "NEXT_ACTION",
    "PAD",
]
METHOD_ACTIONS = ["BIND_CONFIRMED", "RESOLVE_SYSTEM", "ASK_USER", "BLOCK_CONTRADICTION", "NO_ACTION"]
SEMANTIC_ACTIONS = [
    "BIND_ENUM", "EXTRACT_NUMERIC", "ASK_CORRECTION_CONFIRMATION",
    "ASK_DISAMBIGUATION", "REQUEST_CONTEXT", "BLOCK_CONTRADICTION",
    "ABSTAIN_OUT_OF_CONTRACT", "OTHER",
]
ACTIONS = ["REGENERATE_AND_VALIDATE", "AWAIT_USER_REQUIREMENTS", "RETRIEVE_SYSTEM_CONTEXT", "INTERNAL_STATE_RECONCILIATION_REQUIRED", "OTHER"]
TIERS = ["openrouter", "ollama", "rule_based", "abstain", "unknown"]
MAX_STEPS = 7


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def one_hot(value: str, options: list[str]) -> list[float]:
    return [1.0 if value == item else 0.0 for item in options]


def _provider_tier(item: dict[str, Any]) -> str:
    provider = (item.get("classification") or {}).get("provider") or {}
    tier = str(provider.get("selected_tier") or "unknown")
    return tier if tier in TIERS else "unknown"


def vectorize(item: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    """Return [MAX_STEPS, channels] local step features and valid-step mask."""
    classification = item.get("classification") or {}
    deterministic = item.get("deterministic_validation") or {}
    accepted = classification.get("accepted") or {}
    rejected = classification.get("rejected") or []
    allowed_fields = classification.get("allowed_fields") or []
    deterministic_values = item.get("deterministic_values") or {}
    bound = set(item.get("semantic_bound_fields") or [])
    contradictions = item.get("contradictions") or []
    remaining = item.get("remaining_requirements") or []
    machine_authorized = bool(item.get("machine_authorized"))
    tier = _provider_tier(item)
    steps = list(item.get("steps") or [])

    rows: list[list[float]] = []
    mask: list[float] = []
    for idx in range(MAX_STEPS):
        if idx < len(steps):
            step = steps[idx] or {}
            stage = str(step.get("stage") or "PAD")
            valid = 1.0
        else:
            step = {}
            stage = "PAD"
            valid = 0.0
        row: list[float] = []
        row.extend(one_hot(stage, STAGES))
        row.append(valid)
        row.append(idx / max(1, MAX_STEPS - 1))

        # Stage-local facts. This prevents a late failure from contaminating all steps.
        if stage == "DETERMINISTIC_EXTRACT":
            row.extend([
                min(len(deterministic_values), 3) / 3.0,
                1.0 if deterministic.get("valid", True) else 0.0,
                min(len(deterministic.get("rejected") or []), 3) / 3.0,
            ])
        else:
            row.extend([0.0, 0.0, 0.0])

        if stage == "METHOD_POLICY":
            trace = step.get("trace") or item.get("method_policy") or {}
            decisions = trace.get("decisions") or []
            method_action = str((decisions[0] or {}).get("action") if decisions else "NO_ACTION")
            if method_action not in METHOD_ACTIONS:
                method_action = "NO_ACTION"
            row.extend([
                1.0 if trace.get("invoked") else 0.0,
                1.0 if trace.get("language_allowed") else 0.0,
                min(len(trace.get("preexisting_contradictions") or []), 3) / 3.0,
            ])
            row.extend(one_hot(method_action, METHOD_ACTIONS))
        else:
            row.extend([0.0] * (3 + len(METHOD_ACTIONS)))

        if stage == "SEMANTIC_INTERPRET":
            trace = step.get("trace") or item.get("semantic_interpretation") or {}
            decision = trace.get("decision") or {}
            semantic_action = str(decision.get("action") or "OTHER")
            if semantic_action not in SEMANTIC_ACTIONS:
                semantic_action = "OTHER"
            row.extend([
                1.0 if trace.get("invoked") else 0.0,
                1.0 if trace.get("model_available") else 0.0,
                min(len(step.get("observed_fields") or []), 3) / 3.0,
            ])
            row.extend(one_hot(semantic_action, SEMANTIC_ACTIONS))
        else:
            row.extend([0.0] * (3 + len(SEMANTIC_ACTIONS)))

        if stage == "CLOSED_ENUM_CLASSIFY":
            row.extend([
                min(len(accepted), 3) / 3.0,
                min(len(rejected), 3) / 3.0,
                min(len(allowed_fields), 3) / 3.0,
                1.0 if classification.get("abstained") else 0.0,
                1.0 if classification.get("atomic_rejection") else 0.0,
            ])
            row.extend(one_hot(tier, TIERS))
        else:
            row.extend([0.0] * (5 + len(TIERS)))

        if stage == "SEMANTIC_BIND":
            row.extend([
                min(len(bound), 3) / 3.0,
                1.0 if set(accepted).issubset(bound) else 0.0,
            ])
        else:
            row.extend([0.0, 0.0])

        if stage == "CROSS_LAYER_RECONCILE":
            row.extend([
                min(len(contradictions), 3) / 3.0,
                1.0 if not contradictions else 0.0,
            ])
        else:
            row.extend([0.0, 0.0])

        if stage == "NEXT_ACTION":
            action = str(step.get("action") or "OTHER")
            if action not in ACTIONS:
                action = "OTHER"
            row.extend([
                min(len(remaining), 3) / 3.0,
                1.0 if machine_authorized else 0.0,
            ])
            row.extend(one_hot(action, ACTIONS))
        else:
            row.extend([0.0] * (2 + len(ACTIONS)))
        rows.append(row)
        mask.append(valid)
    return np.asarray(rows, dtype=np.float32), np.asarray(mask, dtype=np.float32)


class CDEFunc(nn.Module):
    def __init__(self, hidden_channels: int, input_channels: int) -> None:
        super().__init__()
        self.hidden_channels = hidden_channels
        self.input_channels = input_channels
        self.net = nn.Sequential(
            nn.Linear(hidden_channels, 64),
            nn.Tanh(),
            nn.Linear(64, 64),
            nn.Tanh(),
            nn.Linear(64, hidden_channels * input_channels),
        )

    def forward(self, t: torch.Tensor, z: torch.Tensor) -> torch.Tensor:
        return self.net(z).view(*z.shape[:-1], self.hidden_channels, self.input_channels)


class GatedSpline:
    """Cubic-spline control whose derivative is gated as in OAT Eq. 8."""
    def __init__(self, spline: torchcde.CubicSpline, gate: nn.Module) -> None:
        self.spline = spline
        self.gate = gate
        self.interval = spline.interval

    def evaluate(self, t: torch.Tensor) -> torch.Tensor:
        return self.spline.evaluate(t)

    def derivative(self, t: torch.Tensor) -> torch.Tensor:
        dx = self.spline.derivative(t)
        return torch.sigmoid(self.gate(dx)) * dx


class OATNeuralCDE(nn.Module):
    def __init__(self, channels: int, hidden_channels: int = 16) -> None:
        super().__init__()
        self.channels = channels
        self.hidden_channels = hidden_channels
        self.initial = nn.Linear(channels + 1, hidden_channels)
        self.func = CDEFunc(hidden_channels, channels + 1)
        self.gate = nn.Sequential(
            nn.Linear(channels + 1, 64),
            nn.Tanh(),
            nn.Linear(64, channels + 1),
        )
        self.readout = nn.Linear(hidden_channels, channels)

    def forward(self, x0: torch.Tensor, dxdt: torch.Tensor) -> torch.Tensor:
        """Integrate a gated Neural CDE with precomputed cubic-spline derivatives."""
        z = self.initial(x0)
        states = [z]
        for idx in range(dxdt.shape[1]):
            local_dxdt = dxdt[:, idx]
            gated_dxdt = torch.sigmoid(self.gate(local_dxdt)) * local_dxdt
            vector_field = self.func(torch.tensor(float(idx), device=z.device), z)
            dzdt = torch.bmm(vector_field, gated_dxdt.unsqueeze(-1)).squeeze(-1)
            z = z + dzdt
            states.append(z)
        return self.readout(torch.stack(states, dim=1))


@dataclass
class Standardizer:
    mean: np.ndarray
    std: np.ndarray

    @classmethod
    def fit(cls, x: np.ndarray, mask: np.ndarray) -> "Standardizer":
        valid = x[mask.astype(bool)]
        mean = valid.mean(axis=0)
        std = valid.std(axis=0)
        std[std < 1e-5] = 1.0
        return cls(mean.astype(np.float32), std.astype(np.float32))

    def transform(self, x: np.ndarray) -> np.ndarray:
        return ((x - self.mean) / self.std).astype(np.float32)


def batch_arrays(rows: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray]:
    vectors, masks = zip(*(vectorize(row) for row in rows))
    return np.stack(vectors), np.stack(masks)


def precompute_controls(x: np.ndarray) -> tuple[torch.Tensor, torch.Tensor]:
    """Precompute natural-cubic control state and midpoint derivatives once."""
    target = torch.from_numpy(x)
    batch, steps, _ = target.shape
    grid = torch.arange(steps, dtype=target.dtype)
    tnorm = torch.linspace(0.0, 1.0, steps, dtype=target.dtype)
    time_channel = tnorm.view(1, steps, 1).expand(batch, -1, -1)
    control = torch.cat([target, time_channel], dim=-1)
    with torch.no_grad():
        coeffs = torchcde.natural_cubic_coeffs(control, t=grid)
        spline = torchcde.CubicSpline(coeffs, t=grid)
        x0 = spline.evaluate(grid[0])
        mids = [(grid[j] + grid[j + 1]) / 2 for j in range(steps - 1)]
        dxdt = torch.stack([spline.derivative(mid) for mid in mids], dim=1)
    return x0, dxdt


def step_errors(model: nn.Module, x0: torch.Tensor, dxdt: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    model.eval()
    with torch.no_grad():
        pred = model(x0, dxdt)
        return ((pred - target) ** 2).mean(dim=-1)


def set_metrics(pred_sets: list[set[int]], true_sets: list[set[int]]) -> dict[str, float]:
    ps, rs, fs, hits, dists = [], [], [], [], []
    for pred, true in zip(pred_sets, true_sets):
        tp = len(pred & true)
        p = tp / len(pred) if pred else 0.0
        r = tp / len(true) if true else 0.0
        f = 2 * p * r / (p + r) if (p + r) else 0.0
        ps.append(p); rs.append(r); fs.append(f); hits.append(1.0 if tp else 0.0)
        if pred and true:
            dists.append(float(min(abs(a - b) for a in pred for b in true)))
        else:
            dists.append(float(MAX_STEPS))
    return {
        "precision": float(np.mean(ps)),
        "recall": float(np.mean(rs)),
        "f1": float(np.mean(fs)),
        "hit_rate": float(np.mean(hits)),
        "localization_distance": float(np.mean(dists)),
    }


def train_once(
    success_rows: list[dict[str, Any]],
    failure_rows: list[dict[str, Any]],
    *,
    seed: int,
    epochs: int,
    alpha: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    order = np.random.permutation(len(success_rows))
    n_train = max(80, int(len(order) * 0.8))
    train_rows = [success_rows[i] for i in order[:n_train]]
    cal_rows = [success_rows[i] for i in order[n_train:]]

    train_x, train_mask = batch_arrays(train_rows)
    cal_x, cal_mask = batch_arrays(cal_rows)
    fail_x, fail_mask = batch_arrays(failure_rows)
    scaler = Standardizer.fit(train_x, train_mask)
    train_x = scaler.transform(train_x)
    cal_x = scaler.transform(cal_x)
    fail_x = scaler.transform(fail_x)

    device = torch.device("cpu")
    model = OATNeuralCDE(channels=train_x.shape[-1], hidden_channels=16).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
    x_t = torch.from_numpy(train_x).to(device)
    m_t = torch.from_numpy(train_mask).to(device)
    train_x0, train_dxdt = precompute_controls(train_x)
    cal_x0, cal_dxdt = precompute_controls(cal_x)
    fail_x0, fail_dxdt = precompute_controls(fail_x)
    train_x0 = train_x0.to(device); train_dxdt = train_dxdt.to(device)
    best_loss = math.inf
    best_state: dict[str, torch.Tensor] | None = None
    patience = 15
    stale = 0
    history: list[float] = []
    started = time.time()
    for epoch in range(epochs):
        model.train()
        perm = torch.randperm(x_t.shape[0])
        epoch_losses = []
        for start in range(0, len(perm), 48):
            idx = perm[start:start + 48]
            xb = x_t[idx]
            mb = m_t[idx]
            pred = model(train_x0[idx], train_dxdt[idx])
            per_step = ((pred - xb) ** 2).mean(dim=-1)
            loss = (per_step * mb).sum() / mb.sum().clamp_min(1.0)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            opt.step()
            epoch_losses.append(float(loss.detach()))
        loss_value = float(np.mean(epoch_losses))
        history.append(loss_value)
        if loss_value < best_loss - 1e-5:
            best_loss = loss_value
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            stale = 0
        else:
            stale += 1
        if stale >= patience:
            break
    if best_state is not None:
        model.load_state_dict(best_state)

    cal_err = step_errors(model, cal_x0, cal_dxdt, torch.from_numpy(cal_x)).numpy()
    fail_err = step_errors(model, fail_x0, fail_dxdt, torch.from_numpy(fail_x)).numpy()
    valid_cal_scores = cal_err[cal_mask.astype(bool)]
    threshold = float(np.quantile(valid_cal_scores, 1.0 - alpha, method="higher"))

    pred_sets: list[set[int]] = []
    true_sets: list[set[int]] = []
    flat_scores: list[float] = []
    flat_labels: list[int] = []
    per_failure: list[dict[str, Any]] = []
    for row, errors, mask in zip(failure_rows, fail_err, fail_mask):
        valid = int(mask.sum())
        predicted = {i for i in range(valid) if float(errors[i]) > threshold}
        labels = set(int(i) for i in ((row.get("failure_meta") or {}).get("error_steps") or []))
        pred_sets.append(predicted); true_sets.append(labels)
        for i in range(valid):
            flat_scores.append(float(errors[i]))
            flat_labels.append(1 if i in labels else 0)
        per_failure.append({
            "fault": (row.get("failure_meta") or {}).get("fault"),
            "scores": [float(v) for v in errors[:valid]],
            "predicted_steps": sorted(predicted),
            "true_steps": sorted(labels),
        })

    metrics = set_metrics(pred_sets, true_sets)
    metrics["auroc"] = float(roc_auc_score(flat_labels, flat_scores))
    metrics["auprc"] = float(average_precision_score(flat_labels, flat_scores))
    # Empirical false-positive rate on held-out success steps.
    metrics["success_false_positive_rate"] = float(np.mean(valid_cal_scores > threshold))
    metrics["threshold"] = threshold
    metrics["train_loss"] = best_loss
    metrics["epochs_ran"] = len(history)
    metrics["training_seconds"] = time.time() - started
    metrics["seed"] = seed
    metrics["train_successes"] = len(train_rows)
    metrics["calibration_successes"] = len(cal_rows)
    model_artifact = {
        "state_dict": model.state_dict(),
        "mean": scaler.mean,
        "std": scaler.std,
        "threshold": threshold,
        "channels": train_x.shape[-1],
        "seed": seed,
    }
    details = {"metrics": metrics, "failures": per_failure, "history": history}
    return details, model_artifact


def aggregate(runs: list[dict[str, Any]]) -> dict[str, Any]:
    keys = ["precision", "recall", "f1", "hit_rate", "auroc", "auprc", "localization_distance", "success_false_positive_rate"]
    out: dict[str, Any] = {}
    for key in keys:
        vals = np.asarray([r["metrics"][key] for r in runs], dtype=float)
        out[key] = {"mean": float(vals.mean()), "std": float(vals.std())}
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--success", type=Path, required=True)
    parser.add_argument("--failure", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=220)
    parser.add_argument("--alpha", type=float, default=0.2)
    parser.add_argument("--seeds", default="3407,3408,3409")
    args = parser.parse_args()
    success_rows = read_jsonl(args.success)
    failure_rows = read_jsonl(args.failure)
    seeds = [int(x) for x in args.seeds.split(",") if x.strip()]
    if len(success_rows) < 100:
        raise SystemExit("OAT proof requires at least 100 oracle-approved successes")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    runs: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    for seed in seeds:
        details, artifact = train_once(success_rows, failure_rows, seed=seed, epochs=args.epochs, alpha=args.alpha)
        runs.append(details); artifacts.append(artifact)
        print(json.dumps(details["metrics"], sort_keys=True))

    best_idx = int(np.argmax([run["metrics"]["f1"] for run in runs]))
    torch.save(artifacts[best_idx], args.output_dir / "oat_neural_cde.pt")
    report = {
        "schema": "project-oat-neural-cde-proof-v1",
        "implementation": "independent reproduction using torchcde; not authors' official code",
        "representation": "structured project-state step vectors, not Qwen hidden states",
        "training_data": {"successes": len(success_rows), "failure_labels_used_for_training": False},
        "evaluation_data": {"failures": len(failure_rows), "labels_used_only_after_training": True},
        "architecture": {
            "type": "gated_neural_cde_reconstruction",
            "vector_field": "3-layer MLP, hidden 64",
            "latent_channels": 16,
            "interpolation": "natural cubic spline",
            "solver": "Euler",
            "conformal_alpha": args.alpha,
        },
        "runs": [run["metrics"] for run in runs],
        "aggregate": aggregate(runs),
        "best_seed": runs[best_idx]["metrics"]["seed"],
        "best_failure_details": runs[best_idx]["failures"],
    }
    # Empirical proof gate, deliberately not universal correctness.
    agg = report["aggregate"]
    report["empirical_gate"] = {
        "auroc_at_least_0_70": agg["auroc"]["mean"] >= 0.70,
        "hit_rate_at_least_0_70": agg["hit_rate"]["mean"] >= 0.70,
        "false_positive_at_most_0_30": agg["success_false_positive_rate"]["mean"] <= 0.30,
    }
    report["passed"] = all(report["empirical_gate"].values())
    (args.output_dir / "OAT_NEURAL_CDE_REPORT.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"passed": report["passed"], "aggregate": report["aggregate"]}, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
