"""Standalone, headless LSTM training — mirrors notebooks/02_lstm_model.ipynb exactly.

The notebook is Colab-only (clones this repo, needs a GPU runtime to be
fast). This script runs the identical logic locally/in the dev container, so
training doesn't require a Colab session — CPU-only here, so budget roughly
10x the notebook's own GPU timings (see docs/training-notes.md).

Two modes, both reading every hyperparameter from config/model_config.yaml:

  --calibrate   5 epochs on a stratified 20% subset of the training split —
                a cheap correctness check (does it learn at all, or collapse
                to predicting one class) before committing to the long run.
                Writes results/calibration_run_02_geo.json.

  --full        The real run: all configured epochs on the full training
                split. Writes models/lstm_checkpoint_best.pt (best val_acc),
                models/lstm_final.pt (last epoch), and
                results/training_history_geo.json.

Usage (inside the dev container, which has torch==2.3.0+cpu)::

    docker compose --profile dev run --rm dev python -m scripts.train_lstm --calibrate
    docker compose --profile dev run --rm dev python -m scripts.train_lstm --full
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import yaml
from sklearn.model_selection import train_test_split
from torch.utils.data import DataLoader, TensorDataset, WeightedRandomSampler

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models.lstm_model import build_model  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "model_config.yaml"
DATA_DIR = ROOT / "data" / "processed"
MODELS_DIR = ROOT / "models"
RESULTS_DIR = ROOT / "results"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def load_arrays() -> tuple[np.ndarray, ...]:
    X_train = np.load(DATA_DIR / "X_train.npy").astype(np.float32)
    y_train = np.load(DATA_DIR / "y_train.npy").astype(np.float32)
    X_val = np.load(DATA_DIR / "X_val.npy").astype(np.float32)
    y_val = np.load(DATA_DIR / "y_val.npy").astype(np.float32)
    logger.info("X_train: %s  y_train: %s", X_train.shape, y_train.shape)
    logger.info("X_val:   %s  y_val: %s", X_val.shape, y_val.shape)
    logger.info("Train fraud ratio: %.4f%%", y_train.mean() * 100)
    return X_train, y_train, X_val, y_val


def make_train_loader(X: np.ndarray, y: np.ndarray, batch_size: int) -> DataLoader:
    """Each class gets weight = 1 / class_count, so every batch is ~50/50
    fraud/normal regardless of the true class ratio -- see CLAUDE.md's note
    on the pos_weight=773 collapse this replaced."""
    class_counts = np.bincount(y.astype(int))
    class_weights = 1.0 / class_counts
    sample_weights = torch.tensor(class_weights[y.astype(int)], dtype=torch.float32)
    sampler = WeightedRandomSampler(sample_weights, num_samples=len(sample_weights), replacement=True)
    ds = TensorDataset(torch.from_numpy(X), torch.from_numpy(y))
    return DataLoader(ds, batch_size=batch_size, sampler=sampler)


def make_eval_loader(X: np.ndarray, y: np.ndarray, batch_size: int) -> DataLoader:
    ds = TensorDataset(torch.from_numpy(X), torch.from_numpy(y))
    return DataLoader(ds, batch_size=batch_size, shuffle=False)


def train_epoch(model, loader, optimizer, criterion, device) -> tuple[float, float]:
    model.train()
    total_loss, correct, total = 0.0, 0, 0
    for X_batch, y_batch in loader:
        X_batch, y_batch = X_batch.to(device), y_batch.to(device)
        optimizer.zero_grad()
        logits = model(X_batch)
        loss = criterion(logits, y_batch)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()
        total_loss += loss.item() * len(y_batch)
        preds = (torch.sigmoid(logits) >= 0.5).long()
        correct += (preds == y_batch.long()).sum().item()
        total += len(y_batch)
    return total_loss / total, correct / total


def eval_epoch(model, loader, criterion, device) -> tuple[float, float]:
    model.eval()
    total_loss, correct, total = 0.0, 0, 0
    with torch.no_grad():
        for X_batch, y_batch in loader:
            X_batch, y_batch = X_batch.to(device), y_batch.to(device)
            logits = model(X_batch)
            loss = criterion(logits, y_batch)
            total_loss += loss.item() * len(y_batch)
            preds = (torch.sigmoid(logits) >= 0.5).long()
            correct += (preds == y_batch.long()).sum().item()
            total += len(y_batch)
    return total_loss / total, correct / total


def run_calibration(cfg: dict, X_train, y_train, X_val, y_val, device) -> None:
    t = cfg["training"]
    pos_weight_val = cfg["loss"]["pos_weight"]

    idx = np.arange(len(X_train))
    idx_calib, _ = train_test_split(
        idx, train_size=t["calibration_subset"], stratify=y_train.astype(int), random_state=t["seed"]
    )
    X_calib, y_calib = X_train[idx_calib], y_train[idx_calib]
    calib_loader = make_train_loader(X_calib, y_calib, t["batch_size"])
    val_loader = make_eval_loader(X_val, y_val, t["batch_size"])
    logger.info(
        "Calibration subset: %s samples (fraud: %.4f%%)",
        f"{len(X_calib):,}", y_calib.mean() * 100,
    )

    torch.manual_seed(t["seed"])
    model = build_model(cfg).to(device)
    criterion = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([pos_weight_val], device=device))
    optimizer = torch.optim.Adam(model.parameters(), lr=t["learning_rate"])

    history = []
    logger.info("Calibration: %s epochs on %.0f%% of real PaySim (13 features)\n",
                t["calibration_epochs"], t["calibration_subset"] * 100)
    for epoch in range(1, t["calibration_epochs"] + 1):
        t0 = time.time()
        tr_loss, tr_acc = train_epoch(model, calib_loader, optimizer, criterion, device)
        vl_loss, vl_acc = eval_epoch(model, val_loader, criterion, device)
        elapsed = time.time() - t0
        logger.info(
            "Epoch %d/%d  train_loss=%.4f  train_acc=%.4f%%  val_loss=%.4f  val_acc=%.4f%%  (%.1fs)",
            epoch, t["calibration_epochs"], tr_loss, tr_acc * 100, vl_loss, vl_acc * 100, elapsed,
        )
        history.append({
            "epoch": epoch, "train_loss": tr_loss, "train_accuracy": tr_acc,
            "val_loss": vl_loss, "val_accuracy": vl_acc, "elapsed_s": round(elapsed, 2),
        })

    RESULTS_DIR.mkdir(exist_ok=True)
    out_path = RESULTS_DIR / "calibration_run_02_geo.json"
    with open(out_path, "w") as f:
        json.dump({
            "run": "calibration_run_02_geo",
            "data": "PaySim real (ealaxi/paysim1)",
            "feature_count": cfg["model"]["input_features"],
            "note": "13-feature pipeline including synthetic geo_velocity_kmh",
            "subset_fraction": t["calibration_subset"],
            "epochs": t["calibration_epochs"],
            "pos_weight": pos_weight_val,
            "final_val_accuracy": history[-1]["val_accuracy"],
            "final_val_loss": history[-1]["val_loss"],
            "history": history,
        }, f, indent=2)
    logger.info("\nCalibration complete. Saved: %s", out_path)


def run_full(cfg: dict, X_train, y_train, X_val, y_val, device) -> None:
    t = cfg["training"]
    pos_weight_val = cfg["loss"]["pos_weight"]

    train_loader = make_train_loader(X_train, y_train, t["batch_size"])
    val_loader = make_eval_loader(X_val, y_val, t["batch_size"])

    torch.manual_seed(t["seed"])
    model = build_model(cfg).to(device)
    criterion = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([pos_weight_val], device=device))
    optimizer = torch.optim.Adam(model.parameters(), lr=t["learning_rate"])
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=2, factor=0.5)

    history = []
    best_val_acc = 0.0
    MODELS_DIR.mkdir(exist_ok=True)

    epochs = t["epochs"]
    logger.info("Full training: %d epochs on %s samples (13 features, real PaySim)\n",
                epochs, f"{len(X_train):,}")

    for epoch in range(1, epochs + 1):
        t0 = time.time()
        tr_loss, tr_acc = train_epoch(model, train_loader, optimizer, criterion, device)
        vl_loss, vl_acc = eval_epoch(model, val_loader, criterion, device)
        scheduler.step(vl_loss)
        elapsed = time.time() - t0

        logger.info(
            "Epoch %02d/%d  train_loss=%.4f  train_acc=%.4f%%  val_loss=%.4f  val_acc=%.4f%%  (%.1fs)",
            epoch, epochs, tr_loss, tr_acc * 100, vl_loss, vl_acc * 100, elapsed,
        )
        history.append({
            "epoch": epoch, "train_loss": tr_loss, "train_accuracy": tr_acc,
            "val_loss": vl_loss, "val_accuracy": vl_acc, "elapsed_s": round(elapsed, 2),
        })

        if vl_acc > best_val_acc:
            best_val_acc = vl_acc
            torch.save(model.state_dict(), MODELS_DIR / "lstm_checkpoint_best.pt")
            logger.info("  -> New best val_acc=%.4f%% -- checkpoint saved", vl_acc * 100)

    torch.save(model.state_dict(), MODELS_DIR / "lstm_final.pt")
    RESULTS_DIR.mkdir(exist_ok=True)
    with open(RESULTS_DIR / "training_history_geo.json", "w") as f:
        json.dump({
            "epochs": epochs,
            "pos_weight": pos_weight_val,
            "feature_count": cfg["model"]["input_features"],
            "note": "13-feature pipeline including synthetic geo_velocity_kmh",
            "history": history,
        }, f, indent=2)

    logger.info("\nDone. Best val_acc: %.4f%%", best_val_acc * 100)
    logger.info("Saved: models/lstm_final.pt  models/lstm_checkpoint_best.pt  results/training_history_geo.json")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--calibrate", action="store_true", help="5-epoch, 20%%-subset correctness check")
    parser.add_argument("--full", action="store_true", help="full training run, all configured epochs")
    args = parser.parse_args()

    if args.calibrate == args.full:
        parser.error("pass exactly one of --calibrate or --full")

    cfg = load_config()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info("Device: %s", device)
    if device.type != "cuda":
        logger.info("No GPU -- expect roughly 10x the Colab GPU timings in docs/training-notes.md.")

    X_train, y_train, X_val, y_val = load_arrays()

    if X_train.shape[2] != cfg["model"]["input_features"]:
        logger.error(
            "data/processed/X_train.npy has %d features but config/model_config.yaml "
            "says input_features=%d. Re-run src.pipeline.run_pipeline to regenerate the "
            "training arrays against the current feature set.",
            X_train.shape[2], cfg["model"]["input_features"],
        )
        return 1

    if args.calibrate:
        run_calibration(cfg, X_train, y_train, X_val, y_val, device)
    else:
        run_full(cfg, X_train, y_train, X_val, y_val, device)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
