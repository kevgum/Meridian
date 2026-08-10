"""Prove ``models/feature_scaler.json`` is the range the LSTM was trained on.

The scaler was recovered after the fact -- training discarded it -- so it needs a
check stronger than "it loads". This script rebuilds the exact test split
``src.pipeline.run_pipeline`` produced, scores it through the trained checkpoint,
and compares the result against ``models/MODEL_CARD.md``.

The logic: the reported metrics are a fingerprint of the scaling. Feed the model
a differently-scaled test set and accuracy, FPR and recall all move together. If
all three land on the card's numbers, the recovered range is the trained one --
there is no plausible way to hit that triple by accident.

Reproducing the split requires matching training bit for bit:

* the same stratified 2,000,000-row sample (``random_state=42``),
* the same feature order and arithmetic,
* the same sequence ordering, since ``train_test_split`` permutes by position,
* the same 70/15/15 stratified split (``random_state=42``).

Sequence building is vectorised. In this sample no customer has more than two
transactions, so ``engineer_features`` takes its zero-padding branch for every
group -- a million-iteration Python loop doing work that is one scatter-assign.
``--verify`` checks the vectorised builder against the original loop.

Usage::

    python -m scripts.validate_feature_scaler --verify 40000
    python -m scripts.validate_feature_scaler
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models.lstm_model import LSTMFraudDetector  # noqa: E402
from src.pipeline.feature_engineering import (  # noqa: E402
    DEFAULT_SCALER_PATH,
    FEATURE_COLS,
    SEQ_LEN,
    compute_feature_matrix,
    load_scaler,
)
from src.pipeline.pii_obfuscation import obfuscate_pii  # noqa: E402
from src.pipeline.run_pipeline import PAYSIM_CSV, load_paysim  # noqa: E402
from scripts.fit_feature_scaler import compute_raw_features  # noqa: E402

logger = logging.getLogger(__name__)

TRAINING_SAMPLE_ROWS = 2_000_000
CHECKPOINT = Path(__file__).resolve().parents[1] / "models" / "lstm_checkpoint_best.pt"
DECISION_THRESHOLD = 0.92

# models/MODEL_CARD.md, "Performance on Test Set".
CARD_METRICS = {
    "accuracy": 98.8578,
    "false_positive_rate": 1.0969,
    "precision": 6.9932,
    "recall": 63.8243,
    "true_positives": 247,
    "false_positives": 3285,
}


def build_sequences_loop(X_scaled: np.ndarray, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
    """The original sliding-window builder, lifted verbatim from engineer_features.

    Kept here only as the reference that ``--verify`` compares against.

    Args:
        X_scaled: Per-row scaled features, positionally aligned to ``df``.
        df: The sorted frame the rows came from.

    Returns:
        Sequences of shape [n, SEQ_LEN, len(FEATURE_COLS)] and their labels.
    """
    X_seq, y_seq = [], []
    for _, group in df.groupby('nameOrig'):
        x_group = X_scaled[group.index]
        y_group = group['isFraud'].values
        if len(x_group) >= SEQ_LEN:
            for i in range(len(x_group) - SEQ_LEN + 1):
                X_seq.append(x_group[i:i + SEQ_LEN])
                y_seq.append(y_group[i + SEQ_LEN - 1])
        else:
            pad_x = np.zeros((SEQ_LEN - len(x_group), len(FEATURE_COLS)))
            X_seq.append(np.vstack([pad_x, x_group]))
            y_seq.append(y_group[-1])
    return np.array(X_seq), np.array(y_seq)


def build_sequences_fast(X_scaled: np.ndarray, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
    """Vectorised equivalent of ``build_sequences_loop`` for short groups.

    Every group shorter than ``SEQ_LEN`` becomes exactly one zero-front-padded
    sequence labelled by its final row, which is a single scatter-assign rather
    than a per-group Python iteration. Groups long enough to slide fall back to
    the reference implementation, so the output is correct for any input.

    ``df`` arrives sorted by ``nameOrig``, and the reference iterates
    ``groupby(...)`` with its default ``sort=True``; group order is therefore the
    frame's own order. Preserving it matters because ``train_test_split``
    partitions by position.

    Args:
        X_scaled: Per-row scaled features, positionally aligned to ``df``.
        df: The sorted frame the rows came from.

    Returns:
        Sequences of shape [n, SEQ_LEN, len(FEATURE_COLS)] and their labels.
    """
    codes, _ = pd.factorize(df['nameOrig'], sort=False)
    n_groups = int(codes.max()) + 1
    sizes = np.bincount(codes)

    if (sizes >= SEQ_LEN).any():
        logger.warning("Groups of >= %d rows present; using the reference builder.", SEQ_LEN)
        return build_sequences_loop(X_scaled, df)

    within = np.arange(len(codes)) - np.repeat(np.concatenate([[0], np.cumsum(sizes)[:-1]]), sizes)
    slot = SEQ_LEN - sizes[codes] + within

    X_seq = np.zeros((n_groups, SEQ_LEN, X_scaled.shape[1]), dtype=X_scaled.dtype)
    X_seq[codes, slot] = X_scaled

    # Label is the group's last row; rows are in order, so the last write wins.
    y_seq = np.zeros(n_groups, dtype=df['isFraud'].to_numpy().dtype)
    y_seq[codes] = df['isFraud'].to_numpy()
    return X_seq, y_seq


def verify(csv_path: str, rows: int) -> bool:
    """Check the vectorised sequence builder against the original loop.

    Args:
        csv_path: PaySim CSV location.
        rows: Sample size for the comparison.

    Returns:
        True when sequences and labels match exactly.
    """
    logger.info("Verifying sequence builder on %s rows...", f"{rows:,}")
    df = load_paysim(csv_path, sample=rows)
    X_scaled, sorted_df = compute_feature_matrix(df, scaler_path=None, fit=True)

    t0 = time.perf_counter()
    X_ref, y_ref = build_sequences_loop(X_scaled, sorted_df)
    slow = time.perf_counter() - t0

    t0 = time.perf_counter()
    X_fast, y_fast = build_sequences_fast(X_scaled, sorted_df)
    fast = time.perf_counter() - t0

    print(f"\n  loop:  {slow:8.2f}s  -> {X_ref.shape}")
    print(f"  fast:  {fast:8.2f}s  -> {X_fast.shape}  ({slow / max(fast, 1e-9):.0f}x)")

    if X_ref.shape != X_fast.shape:
        print("  SHAPE MISMATCH\n")
        return False

    x_diff = float(np.max(np.abs(X_ref - X_fast)))
    y_diff = int(np.sum(y_ref != y_fast))
    print(f"  max abs sequence diff : {x_diff:.3e}")
    print(f"  label mismatches      : {y_diff}\n")
    return x_diff == 0.0 and y_diff == 0


def score(X: np.ndarray, batch: int = 8192) -> np.ndarray:
    """Run sequences through the trained checkpoint and return probabilities.

    Args:
        X: Sequences of shape [n, SEQ_LEN, len(FEATURE_COLS)].
        batch: Rows per forward pass.

    Returns:
        Sigmoid probabilities of shape [n].
    """
    model = LSTMFraudDetector(input_size=len(FEATURE_COLS))
    state = torch.load(CHECKPOINT, map_location='cpu', weights_only=False)
    if isinstance(state, dict) and 'model_state_dict' in state:
        state = state['model_state_dict']
    elif isinstance(state, dict) and 'state_dict' in state:
        state = state['state_dict']
    model.load_state_dict(state)
    model.eval()  # dropout off -- training-mode dropout would make this nondeterministic

    out = np.empty(len(X), dtype=np.float64)
    with torch.no_grad():
        for i in range(0, len(X), batch):
            chunk = torch.from_numpy(np.ascontiguousarray(X[i:i + batch], dtype=np.float32))
            out[i:i + batch] = torch.sigmoid(model(chunk)).numpy()
    return out


def main() -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--csv', default=PAYSIM_CSV)
    parser.add_argument('--sample', type=int, default=TRAINING_SAMPLE_ROWS)
    parser.add_argument('--scaler', default=str(DEFAULT_SCALER_PATH))
    parser.add_argument('--threshold', type=float, default=DECISION_THRESHOLD)
    parser.add_argument('--verify', type=int, metavar='ROWS', default=0)
    parser.add_argument('--no-obfuscate', dest='obfuscate', action='store_false',
                        help='Skip PII hashing. Changes the split; for diagnosis only.')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s', stream=sys.stdout)

    if args.verify:
        return 0 if verify(args.csv, args.verify) else 1

    if not Path(args.scaler).exists():
        logger.error("No scaler at %s -- run scripts/fit_feature_scaler.py first.", args.scaler)
        return 1

    df = load_paysim(args.csv, sample=args.sample)

    if args.obfuscate:
        # Training hashes nameOrig/nameDest BEFORE feature engineering
        # (run_pipeline.py), and compute_raw_features sorts by nameOrig. Hashing
        # after would keep the raw-ID sort order and draw a different
        # train_test_split partition -- same sequence pool, wrong 15% held out.
        logger.info("Obfuscating PII (matches training's row order)...")
        df = obfuscate_pii(df, ['nameOrig', 'nameDest'])

    logger.info("Computing features...")
    feature_df = compute_raw_features(df)
    X_raw = (
        feature_df[FEATURE_COLS]
        .replace([np.inf, -np.inf], np.nan)
        .fillna(0)
        .to_numpy(dtype=float)
    )

    # fit=False on purpose: this exercises the exact path inference uses, so a
    # broken load_scaler round-trip fails here rather than silently in production.
    scaler = load_scaler(args.scaler)
    X_scaled = scaler.transform(X_raw).astype(np.float32)
    logger.info("Scaled range: [%.4f, %.4f]", X_scaled.min(), X_scaled.max())

    logger.info("Building sequences...")
    X_seq, y_seq = build_sequences_fast(X_scaled, feature_df)
    logger.info("Sequences: %s  fraud: %d (%.4f%%)", X_seq.shape, int(y_seq.sum()), 100 * y_seq.mean())

    # Mirrors run_pipeline.main() exactly.
    X_tmp, X_test, y_tmp, y_test = train_test_split(
        X_seq, y_seq, test_size=0.15, stratify=y_seq, random_state=42)
    del X_seq, X_tmp
    logger.info("Test split: %s  fraud: %d", X_test.shape, int(y_test.sum()))

    logger.info("Scoring through %s...", CHECKPOINT.name)
    probs = score(X_test)

    # Environment-independent sanity check: does the model, under this scaler,
    # actually separate fraud from normal transactions? This doesn't depend on
    # reproducing Colab's exact row sample the way the confusion matrix below
    # does -- a real decision surface separates classes regardless of which 300k
    # rows landed in the test split.
    auc = roc_auc_score(y_test, probs)
    fraud_mean, normal_mean = probs[y_test == 1].mean(), probs[y_test == 0].mean()
    fraud_median, normal_median = np.median(probs[y_test == 1]), np.median(probs[y_test == 0])
    print(f"\n  Class separation (scaling-dependent, sampling-independent):")
    print(f"    ROC AUC              : {auc:.4f}")
    print(f"    mean score  | fraud  : {fraud_mean:.4f}   normal: {normal_mean:.4f}")
    print(f"    median score| fraud  : {fraud_median:.4f}   normal: {normal_median:.4f}")

    pred = (probs >= args.threshold).astype(int)
    tp = int(((pred == 1) & (y_test == 1)).sum())
    fp = int(((pred == 1) & (y_test == 0)).sum())
    tn = int(((pred == 0) & (y_test == 0)).sum())
    fn = int(((pred == 0) & (y_test == 1)).sum())

    got = {
        "accuracy": 100.0 * (tp + tn) / len(y_test),
        "false_positive_rate": 100.0 * fp / max(fp + tn, 1),
        "precision": 100.0 * tp / max(tp + fp, 1),
        "recall": 100.0 * tp / max(tp + fn, 1),
        "true_positives": tp,
        "false_positives": fp,
    }

    print(f"\n  Test set: {len(y_test):,} sequences, threshold {args.threshold}\n")
    print(f"  {'metric':<22} {'model card':>12} {'measured':>12} {'delta':>10}")
    print(f"  {'-' * 22} {'-' * 12} {'-' * 12} {'-' * 10}")

    ok = True
    for key, expected in CARD_METRICS.items():
        actual = got[key]
        delta = actual - expected
        # Counts must match exactly; rates are allowed float-level drift.
        tol = 0 if isinstance(expected, int) else 0.01
        passed = abs(delta) <= tol
        ok &= passed
        fmt = "12.0f" if isinstance(expected, int) else "12.4f"
        print(f"  {key:<22} {expected:{fmt}} {actual:{fmt}} {delta:10.4f}  "
              f"{'ok' if passed else 'MISMATCH'}")

    print(f"\n  TP={tp}  FP={fp}  TN={tn}  FN={fn}")
    print(f"\n  {'SCALER VERIFIED' if ok else 'SCALER DOES NOT REPRODUCE THE MODEL CARD'}\n")

    report = Path(__file__).resolve().parents[1] / "results" / "scaler_validation.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({
        "scaler_path": str(args.scaler),
        "sample_rows": int(len(df)),
        "test_sequences": int(len(y_test)),
        "threshold": args.threshold,
        "model_card": CARD_METRICS,
        "measured": got,
        "confusion": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
        "class_separation": {
            "roc_auc": float(auc),
            "fraud_mean": float(fraud_mean),
            "normal_mean": float(normal_mean),
            "fraud_median": float(fraud_median),
            "normal_median": float(normal_median),
        },
        "verified": bool(ok),
    }, indent=2), encoding="utf-8")
    print(f"  Wrote {report}\n")

    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
