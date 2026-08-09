"""Regenerate ``models/feature_scaler.json`` from the PaySim dataset.

Training (``src.pipeline.run_pipeline``) fitted a MinMaxScaler and threw it away
-- ``engineer_features(df)`` is called there without a ``scaler_path``. Inference
therefore had no way to scale a live transaction into the range the model was
trained on, and refitting on a small batch produced confidently wrong scores.
This script recovers that artifact.

It reproduces the training feature values exactly. Two deliberate departures
from ``run_pipeline``, both of which leave the fitted range bit-identical:

1. PII obfuscation is skipped by default. SHA-256 is injective over the distinct
   ``nameOrig`` values, so the groupby partitions are unchanged; hashing only
   permutes the order groups appear in. Every feature is computed within a group,
   and a min/max is order-invariant, so the scaler is unaffected. Pass
   ``--obfuscate`` to do it the long way anyway.
2. The three per-group aggregations are computed with vectorised equivalents of
   the ``groupby(...).transform(lambda ...)`` calls in ``compute_feature_matrix``.
   PaySim has roughly one group per two rows, which is the worst case for
   ``transform`` with a Python callable -- it pays a per-group interpreter round
   trip about a million times. ``--verify`` proves the equivalence numerically
   against the original implementation before trusting it.

Sequence building is skipped entirely: the scaler is fitted on the per-row
feature matrix, and the sliding window only reshapes rows it has already scaled.

Usage::

    python -m scripts.fit_feature_scaler --verify 40000   # prove equivalence
    python -m scripts.fit_feature_scaler                  # fit and write
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pipeline.feature_engineering import (  # noqa: E402
    DEFAULT_SCALER_PATH,
    FEATURE_COLS,
    compute_feature_matrix,
    save_scaler,
)
from src.pipeline.pii_obfuscation import obfuscate_pii  # noqa: E402
from src.pipeline.run_pipeline import PAYSIM_CSV, load_paysim  # noqa: E402

logger = logging.getLogger(__name__)

TRAINING_SAMPLE_ROWS = 2_000_000


def compute_raw_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute the 12 unscaled features, mirroring ``compute_feature_matrix``.

    Every expression below is an exact algebraic equivalent of its counterpart in
    ``src.pipeline.feature_engineering``; the differences are pandas execution
    paths, not arithmetic. ``--verify`` is the check that keeps that claim true.

    Args:
        df: Raw PaySim-shaped rows.

    Returns:
        The frame sorted as training sorted it, with the 12 feature columns
        added and NaN/inf already replaced by zero.
    """
    df = df.copy()
    df = df.sort_values(['nameOrig', 'step'], kind='stable').reset_index(drop=True)
    by_orig = df.groupby('nameOrig', sort=False)

    # 1. amount_delta -- rolling(10) mean per customer.
    #    groupby.rolling takes a Cython path; the lambda form does not.
    rolling_mean = (
        by_orig['amount']
        .rolling(10, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
        .sort_index()
    )
    df['amount_delta'] = df['amount'] - rolling_mean

    # 2. balance_utilisation_ratio
    df['balance_utilisation_ratio'] = df['newbalanceOrig'] / (df['oldbalanceOrg'] + 1e-6)

    # 3. channel_type_encoded
    channel_map = {'PAYMENT': 0, 'TRANSFER': 1, 'CASH_OUT': 2, 'DEBIT': 3, 'CASH_IN': 4}
    df['channel_type_encoded'] = df['type'].map(channel_map).fillna(0)

    # 4. time_of_day_flag -- step is an hour counter.
    tod = df['step'] % 24
    df['time_of_day_flag'] = np.where((tod >= 8) & (tod <= 22), 0, 1)

    # 5. balance_drop_to_zero
    df['balance_drop_to_zero'] = (
        (df['newbalanceOrig'] < 1.0) & (df['oldbalanceOrg'] > 100)
    ).astype(float)

    # 6. amount_to_balance_ratio
    df['amount_to_balance_ratio'] = df['amount'] / (df['oldbalanceOrg'] + 1e-6)

    # 7. transaction_frequency_1h -- already a Cython path upstream.
    df['transaction_frequency_1h'] = df.groupby(['nameOrig', 'step'])['step'].transform('count')

    # 8. transaction_frequency_24h -- a trailing rolling(24).count() over a column
    #    with no nulls is just the capped within-group position.
    if df['step'].isna().any():
        raise ValueError("'step' contains nulls; the cumcount equivalence no longer holds.")
    df['transaction_frequency_24h'] = (by_orig.cumcount() + 1).clip(upper=24).astype(float)

    # 9. cumulative_spend_ratio
    overall_avg = by_orig['amount'].transform('mean') + 1e-6
    df['cumulative_spend_ratio'] = df['amount'] / overall_avg

    # 10. dest_received_ratio
    df['dest_received_ratio'] = (
        (df['newbalanceDest'] - df['oldbalanceDest']) / (df['amount'] + 1e-6)
    )

    # 11. amount_zscore -- transform('mean')/('std') replace the lambda. Both use
    #     ddof=1, and a single-row group yields NaN std in either form.
    grp_mean = by_orig['amount'].transform('mean')
    grp_std = by_orig['amount'].transform('std')
    df['amount_zscore'] = ((df['amount'] - grp_mean) / (grp_std + 1e-6)).fillna(0)

    # 12. step_norm
    df['step_norm'] = df['step'] / (df['step'].max() + 1e-6)

    return df


def verify(csv_path: str, rows: int) -> bool:
    """Compare the fast feature path against the original on a slice.

    Args:
        csv_path: PaySim CSV location.
        rows: How many rows to sample for the comparison.

    Returns:
        True when every feature matches to within float tolerance.
    """
    logger.info("Verifying fast path against compute_feature_matrix on %s rows...", f"{rows:,}")
    df = load_paysim(csv_path, sample=rows)

    t0 = time.perf_counter()
    _, reference_df = compute_feature_matrix(df, scaler_path=None, fit=True)
    slow_secs = time.perf_counter() - t0

    t0 = time.perf_counter()
    fast_df = compute_raw_features(df)
    fast_secs = time.perf_counter() - t0

    reference = (
        reference_df[FEATURE_COLS].replace([np.inf, -np.inf], np.nan).fillna(0).to_numpy(dtype=float)
    )
    fast = fast_df[FEATURE_COLS].replace([np.inf, -np.inf], np.nan).fillna(0).to_numpy(dtype=float)

    if reference.shape != fast.shape:
        logger.error("Shape mismatch: %s vs %s", reference.shape, fast.shape)
        return False

    print(f"\n  original: {slow_secs:8.2f}s")
    print(f"  fast:     {fast_secs:8.2f}s  ({slow_secs / max(fast_secs, 1e-9):.1f}x)")
    print(f"\n  {'feature':<28} {'max abs diff':>14}   {'scale':>12}")
    print(f"  {'-' * 28} {'-' * 14}   {'-' * 12}")

    ok = True
    for i, name in enumerate(FEATURE_COLS):
        diff = float(np.max(np.abs(reference[:, i] - fast[:, i])))
        scale = float(np.max(np.abs(reference[:, i]))) or 1.0
        # Relative tolerance: float32 inputs make bit-identity too strict a bar.
        passed = diff <= 1e-6 * max(scale, 1.0)
        ok &= passed
        print(f"  {name:<28} {diff:14.3e}   {scale:12.3e}  {'ok' if passed else 'MISMATCH'}")

    print()
    return bool(ok)


def fit(csv_path: str, sample: int, out_path: Path, do_obfuscate: bool) -> None:
    """Fit the MinMaxScaler on the training sample and persist its range.

    Args:
        csv_path: PaySim CSV location.
        sample: Stratified row count -- must match what training used.
        out_path: Destination for the scaler JSON.
        do_obfuscate: Hash the PII columns first, as run_pipeline does.
    """
    df = load_paysim(csv_path, sample=sample)
    if do_obfuscate:
        logger.info("Obfuscating PII (order-only effect on the fitted range)...")
        df = obfuscate_pii(df, ['nameOrig', 'nameDest'])

    logger.info("Computing features over %s rows...", f"{len(df):,}")
    t0 = time.perf_counter()
    feature_df = compute_raw_features(df)
    logger.info("Features computed in %.1fs", time.perf_counter() - t0)

    X_raw = feature_df[FEATURE_COLS].replace([np.inf, -np.inf], np.nan).fillna(0).to_numpy(dtype=float)

    scaler = MinMaxScaler().fit(X_raw)
    save_scaler(scaler, out_path)

    print(f"\n  Wrote {out_path}")
    print(f"  Fitted on {X_raw.shape[0]:,} rows x {X_raw.shape[1]} features\n")
    print(f"  {'feature':<28} {'min':>16} {'max':>16}")
    print(f"  {'-' * 28} {'-' * 16} {'-' * 16}")
    for name, lo, hi in zip(FEATURE_COLS, scaler.data_min_, scaler.data_max_):
        print(f"  {name:<28} {lo:16.6g} {hi:16.6g}")
    print()


def main() -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--csv', default=PAYSIM_CSV, help=f'PaySim CSV path (default: {PAYSIM_CSV})')
    parser.add_argument('--sample', type=int, default=TRAINING_SAMPLE_ROWS,
                        help='Stratified sample size. Must match training.')
    parser.add_argument('--out', default=str(DEFAULT_SCALER_PATH), help='Scaler JSON destination')
    parser.add_argument('--obfuscate', action='store_true',
                        help='Hash PII before computing features, as run_pipeline does')
    parser.add_argument('--verify', type=int, metavar='ROWS', default=0,
                        help='Compare against compute_feature_matrix on ROWS rows, then exit')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s', stream=sys.stdout)

    if not Path(args.csv).exists():
        logger.error("PaySim CSV not found at %s", args.csv)
        return 1

    if args.verify:
        return 0 if verify(args.csv, args.verify) else 1

    fit(args.csv, args.sample, Path(args.out), args.obfuscate)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
