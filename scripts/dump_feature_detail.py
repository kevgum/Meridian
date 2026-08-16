
"""Dump every trained feature with its meaning, training range and live values.

Produces a per-feature breakdown for one legitimate and one fraudulent
transaction, showing the raw engineered value, the MinMax-scaled value the model
actually receives, and the range the scaler was fitted on during training.

Usage::

    docker compose --profile dev run --rm dev python -m scripts.dump_feature_detail
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.disable(logging.CRITICAL)

import pandas as pd  # noqa: E402

from src.pipeline.feature_engineering import (  # noqa: E402
    DEFAULT_SCALER_PATH,
    FEATURE_COLS,
    compute_feature_matrix,
)
from scripts.generate_transaction_batch import attach_history  # noqa: E402

# One line per feature: what it measures, in plain English.
MEANING: dict[str, str] = {
    "amount_delta": "Amount minus this customer's rolling 10-transaction average",
    "balance_utilisation_ratio": "Balance left after the payment, as a fraction of the balance before",
    "channel_type_encoded": "Payment type: PAYMENT=0, TRANSFER=1, CASH_OUT=2, DEBIT=3, CASH_IN=4",
    "time_of_day_flag": "0 = inside business hours, 1 = off-hours",
    "balance_drop_to_zero": "1 if the payment emptied the origin account",
    "amount_to_balance_ratio": "Amount as a fraction of the balance before; fraud takes it all",
    "transaction_frequency_1h": "Transactions by this customer in the same hour bucket",
    "transaction_frequency_24h": "Rolling 24-transaction count for this customer",
    "cumulative_spend_ratio": "Amount divided by this customer's mean transaction amount",
    "dest_received_ratio": "How much the destination actually gained, per unit sent",
    "amount_zscore": "Standard deviations from this customer's own mean amount",
    "step_norm": "Normalised position in time across the dataset",
    "geo_velocity_kmh": "SYNTHETIC fabricated travel speed between consecutive transactions",
}

NOTES: dict[str, str] = {
    "balance_utilisation_ratio": "clipped to [0,5] before scaling (see MODEL_CARD item 6)",
    "amount_to_balance_ratio": "clipped to [0,5] before scaling (see MODEL_CARD item 6)",
    "transaction_frequency_1h": "near-constant in training (range 1-2) - carries little signal",
    "transaction_frequency_24h": "near-constant in training (range 1-2) - carries little signal",
    "geo_velocity_kmh": "SYNTHETIC - PaySim has no location data at all",
}


def values_for(build_session) -> tuple[dict[str, float], dict[str, float]]:
    """Return (raw, scaled) feature values for a session's final transaction.

    ``compute_feature_matrix`` returns the scaled matrix alongside the frame it
    built it from, and that frame still carries the un-scaled engineered
    columns — so both halves come from one call, guaranteeing they describe the
    same row rather than two separately-computed ones.
    """
    txns = build_session()
    attach_history(txns)
    frame = pd.DataFrame([t.paysim_row() for t in txns])
    frame["_i"] = range(len(txns))

    scaled, ordered = compute_feature_matrix(frame, fit=False)
    target_pos = int(ordered[ordered["_i"] == len(txns) - 1].index[0])
    raw_row = ordered.iloc[target_pos]

    return ({c: float(raw_row[c]) for c in FEATURE_COLS},
            {c: float(v) for c, v in zip(FEATURE_COLS, scaled[target_pos])})


def main() -> int:
    from scripts.fifty_dollar_pass_check import build_session as legit
    from scripts.fraud_transaction_fail_check import build_session as fraud

    scaler = json.loads(Path(DEFAULT_SCALER_PATH).read_text(encoding="utf-8"))
    mins = dict(zip(scaler["feature_cols"], scaler["data_min"]))
    maxs = dict(zip(scaler["feature_cols"], scaler["data_max"]))

    legit_raw, legit_scaled = values_for(legit)
    fraud_raw, fraud_scaled = values_for(fraud)

    rows = []
    for i, col in enumerate(FEATURE_COLS, start=1):
        rows.append({
            "n": i,
            "feature": col,
            "meaning": MEANING[col],
            "train_min": mins[col],
            "train_max": maxs[col],
            "legit_raw": legit_raw[col],
            "legit_scaled": legit_scaled[col],
            "fraud_raw": fraud_raw[col],
            "fraud_scaled": fraud_scaled[col],
            "note": NOTES.get(col, ""),
        })

    out = Path("evidence/raw/feature_detail.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    print(f"\n{len(FEATURE_COLS)} TRAINED FEATURES - source of truth: FEATURE_COLS in "
          "src/pipeline/feature_engineering.py\n")
    hdr = (f"{'#':>2}  {'feature':<27} {'train min':>16} {'train max':>16}  "
           f"{'legit':>10} {'fraud':>10}")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{r['n']:>2}  {r['feature']:<27} {r['train_min']:>16.4f} "
              f"{r['train_max']:>16.4f}  {r['legit_scaled']:>10.4f} "
              f"{r['fraud_scaled']:>10.4f}")
    print(f"\nwritten to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
