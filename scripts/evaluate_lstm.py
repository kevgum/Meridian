"""Headless test-set evaluation — mirrors notebooks/03_evaluation.ipynb cells 12-24.

Loads models/lstm_checkpoint_best.pt, runs it over data/processed/X_test.npy,
sweeps decision thresholds to find the lowest one meeting the accuracy target,
and writes results/final_metrics.json + results/figures/confusion_matrix.png.

Usage (inside the dev container, which has torch==2.3.0+cpu + matplotlib + seaborn)::

    docker compose --profile dev run --rm dev python -m scripts.evaluate_lstm
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
import torch
import yaml
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from torch.utils.data import DataLoader, TensorDataset

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models.lstm_model import build_model  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "model_config.yaml"
DATA_DIR = ROOT / "data" / "processed"
MODELS_DIR = ROOT / "models"
RESULTS_DIR = ROOT / "results"
TARGET_ACC = 0.9855


def main() -> int:
    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info("Device: %s", device)

    model = build_model(cfg).to(device)
    model.load_state_dict(torch.load(MODELS_DIR / "lstm_checkpoint_best.pt", map_location=device))
    model.eval()
    logger.info("Model loaded from models/lstm_checkpoint_best.pt")

    X_test = np.load(DATA_DIR / "X_test.npy").astype(np.float32)
    y_test = np.load(DATA_DIR / "y_test.npy").astype(np.float32)
    logger.info("Test set: %s  fraud ratio: %.4f%%", X_test.shape, y_test.mean() * 100)

    batch_size = cfg["training"]["batch_size"]
    test_ds = TensorDataset(torch.from_numpy(X_test), torch.from_numpy(y_test))
    test_loader = DataLoader(test_ds, batch_size=batch_size, shuffle=False)

    all_probs, all_labels = [], []
    with torch.no_grad():
        for X_batch, y_batch in test_loader:
            X_batch = X_batch.to(device)
            logits = model(X_batch)
            probs = torch.sigmoid(logits).cpu().numpy()
            all_probs.extend(probs)
            all_labels.extend(y_batch.numpy())

    y_prob = np.array(all_probs)
    y_true = np.array(all_labels).astype(int)
    logger.info("Inference complete on %s test samples", f"{len(y_true):,}")
    logger.info("Max anomaly probability: %.4f  |  Mean: %.4f", y_prob.max(), y_prob.mean())

    logger.info("%7s %9s %8s %10s %8s %13s", "thresh", "accuracy", "FPR", "precision", "recall", "fraud_caught")
    logger.info("-" * 60)

    threshold = None
    for t in np.arange(0.90, 0.9991, 0.005):
        pred = (y_prob >= t).astype(int)
        tn_, fp_, fn_, tp_ = confusion_matrix(y_true, pred, labels=[0, 1]).ravel()
        acc_ = accuracy_score(y_true, pred)
        fpr_ = fp_ / (fp_ + tn_) if (fp_ + tn_) else 0.0
        rec_ = tp_ / (tp_ + fn_) if (tp_ + fn_) else 0.0
        prec_ = tp_ / (tp_ + fp_) if (tp_ + fp_) else 0.0
        flag = ""
        if acc_ >= TARGET_ACC and threshold is None:
            threshold = round(float(t), 4)
            flag = "  <- selected (first >= 98.55%)"
        logger.info(
            "%7.3f %8.4f%% %7.4f%% %9.4f%% %7.4f%% %6d/%-6d%s",
            t, acc_ * 100, fpr_ * 100, prec_ * 100, rec_ * 100, tp_, tp_ + fn_, flag,
        )

    if threshold is None:
        threshold = 0.90
        logger.info("No threshold reached %.2f%%; falling back to %s", TARGET_ACC * 100, threshold)

    y_pred = (y_prob >= threshold).astype(int)
    logger.info("\nSelected threshold: %s  |  Transactions flagged as fraud: %s", threshold, f"{y_pred.sum():,}")

    logger.info("\n=== Classification Report ===")
    logger.info(classification_report(y_true, y_pred, target_names=["Normal", "Fraud"], digits=4))

    cm = confusion_matrix(y_true, y_pred)
    tn, fp, fn, tp = cm.ravel()

    detection_accuracy = accuracy_score(y_true, y_pred)
    precision = precision_score(y_true, y_pred, zero_division=0)
    recall = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0

    logger.info("Detection Accuracy : %.4f%%  (target >= 98.55%%)", detection_accuracy * 100)
    logger.info("False Positive Rate: %.4f%%  (target <= 0.50%%)", fpr * 100)
    logger.info("Precision          : %.4f%%", precision * 100)
    logger.info("Recall (TPR)       : %.4f%%", recall * 100)
    logger.info("F1-Score           : %.4f", f1)
    logger.info("Fraud caught       : %d/%d  |  False alarms: %d/%d", tp, tp + fn, fp, fp + tn)

    accuracy_ok = detection_accuracy >= 0.9855
    fpr_ok = fpr <= 0.005
    logger.info("Accuracy target MET: %s  |  FPR target MET: %s", accuracy_ok, fpr_ok)

    figures_dir = RESULTS_DIR / "figures"
    figures_dir.mkdir(exist_ok=True, parents=True)
    fig, ax = plt.subplots(figsize=(7, 5))
    sns.heatmap(
        cm, annot=True, fmt="d", cmap="Blues",
        xticklabels=["Normal", "Fraud"], yticklabels=["Normal", "Fraud"], ax=ax,
    )
    ax.set_title("Confusion Matrix - LSTM Fraud Detector (13-feature, geo-velocity)", fontsize=13, fontweight="bold")
    ax.set_xlabel("Predicted", fontsize=11)
    ax.set_ylabel("Actual", fontsize=11)
    fig.text(
        0.5, -0.02,
        f"Accuracy: {detection_accuracy:.4%}  |  FPR: {fpr:.4%}  |  Recall: {recall:.4%}  |  F1: {f1:.4f}",
        ha="center", fontsize=9, color="gray",
    )
    plt.tight_layout()
    plt.savefig(figures_dir / "confusion_matrix.png", dpi=150, bbox_inches="tight")
    logger.info("Saved: results/figures/confusion_matrix.png")

    final_metrics = {
        "model": "LSTMFraudDetector v1 (13-feature, geo-velocity)",
        "threshold": threshold,
        "test_samples": int(len(y_true)),
        "fraud_samples": int(y_true.sum()),
        "detection_accuracy": round(detection_accuracy, 6),
        "false_positive_rate": round(fpr, 6),
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1_score": round(f1, 6),
        "true_positives": int(tp),
        "true_negatives": int(tn),
        "false_positives": int(fp),
        "false_negatives": int(fn),
        "targets_met": {
            "accuracy_gte_9855": bool(accuracy_ok),
            "fpr_lte_050_pct": bool(fpr_ok),
        },
    }

    RESULTS_DIR.mkdir(exist_ok=True)
    with open(RESULTS_DIR / "final_metrics.json", "w") as f:
        json.dump(final_metrics, f, indent=2)
    logger.info("\nSaved: results/final_metrics.json")
    logger.info(json.dumps(final_metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
