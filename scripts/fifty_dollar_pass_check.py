"""Follow one legitimate $50 transaction through the real pipeline, end to end.

The PASS counterpart to fraud_transaction_fail_check.py. Builds a short,
believable session for one customer (four ordinary payments leading up to a
final $50.00 "50 Dollar Pass Check" transaction), then runs the SAME real
components the batch and live-stream scripts use:

  1. Feature engineering  -> compute_feature_matrix (13 trained features, MinMax-scaled)
  2. LSTM inference       -> the served ONNX model, over a raw HTTP call this
                             script prints in full (request + response)
  3. SIEM rule engine     -> ElasticSIEMCorrelator, every rule's verdict printed
  4. Hybrid scorer        -> HybridThreatScorer (lstm*0.60 + siem*0.40)
  5. Playbook             -> fires for real if the blended score crosses 0.70
                             (it should not, here — this transaction is clean)
  6. Elasticsearch        -> the whole session is indexed (with --write), so
                             Kibana and the React dashboard show it live

Dry run (default) evaluates and prints everything, writes nothing::

    docker compose --profile dev run --rm dev python -m scripts.fifty_dollar_pass_check

Live — indexes to Elasticsearch, dashboard/Kibana pick it up::

    docker compose --profile dev run --rm -e ELASTIC_HOST=http://elasticsearch:9200 dev python -m scripts.fifty_dollar_pass_check --write
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.siem.hybrid_scorer import HybridThreatScorer  # noqa: E402
from src.siem.playbook_engine import PlaybookEngine  # noqa: E402
from src.siem.rule_engine import ElasticSIEMCorrelator  # noqa: E402

from scripts.generate_transaction_batch import (  # noqa: E402
    LOCATIONS,
    Txn,
    _build_es,
    _env_value,
    attach_history,
    score_with_model,
    transaction_doc,
)
from src.inference_client import LSTMInferenceClient  # noqa: E402

logging.disable(logging.CRITICAL)

SYDNEY_TZ = ZoneInfo("Australia/Sydney")
CUSTOMER_ID = "CUST-52210"
TARGET_AMOUNT = 50.00


def build_session() -> list[Txn]:
    """Four ordinary payments today, ending in the $50.00 target transaction."""
    now = datetime.now(tz=timezone.utc)
    place = "Sydney, NSW"

    prior = [
        ("M0101", "Coles Supermarkets", 5411, "Grocery Stores", 84.20, 6.0),
        ("M0106", "Opal Transport Top-Up", 4111, "Local Transit", 30.00, 4.3),
        ("M0115", "The Coffee Club", 5814, "Cafes", 12.50, 2.1),
        ("M0104", "Chemist Warehouse", 5912, "Drug Stores", 27.90, 0.8),
    ]

    txns: list[Txn] = []
    balance = 3_240.00
    prev_when = now - timedelta(hours=7)

    for merchant_id, name, mcc, mcc_label, amount, hours_ago in prior:
        when = now - timedelta(hours=hours_ago)
        old_bal = balance
        new_bal = round(old_bal - amount, 2)
        txns.append(Txn(
            customer_id=CUSTOMER_ID, amount=amount,
            merchant=(merchant_id, name, mcc, mcc_label),
            location=place, prev_location=place,
            when=when, prev_when=prev_when,
            channel="Card", txn_type="PAYMENT",
            profile="routine", intent="ordinary payment",
            old_balance_orig=old_bal, new_balance_orig=new_bal,
            old_balance_dest=round(old_bal * 0.3, 2),
            new_balance_dest=round(old_bal * 0.3 + amount, 2),
            is_fraud=0,
        ))
        balance = new_bal
        prev_when = when

    # -- The target transaction: $50.00 at a service station, just now --------
    when = now
    old_bal = balance
    new_bal = round(old_bal - TARGET_AMOUNT, 2)
    target = Txn(
        customer_id=CUSTOMER_ID, amount=TARGET_AMOUNT,
        merchant=("M0105", "50 Dollar Pass Check", 5541, "Service Stations"),
        location=place, prev_location=place,
        when=when, prev_when=prev_when,
        channel="Card", txn_type="PAYMENT",
        profile="routine", intent="50 dollar pass check",
        old_balance_orig=old_bal, new_balance_orig=new_bal,
        old_balance_dest=round(old_bal * 0.3, 2),
        new_balance_dest=round(old_bal * 0.3 + TARGET_AMOUNT, 2),
        is_fraud=0,
    )
    txns.append(target)
    return txns


def show_raw_api_call(window, base_url: str) -> float:
    """Call the LSTM predict endpoint directly with requests, printing the
    exact request and response so the console output IS the API log."""
    payload = {"instances": [window.tolist()]}
    url = f"{base_url}/v1/models/lstm:predict"

    print("=" * 78)
    print("STEP 2 — LSTM inference API call")
    print("=" * 78)
    print(f"POST {url}")
    print("Content-Type: application/json\n")
    print("Request body (instances: [1, 5, 13] — 5-transaction window, 13 features each):")
    print(json.dumps(payload, indent=2)[:1400], "...\n" if len(json.dumps(payload)) > 1400 else "\n")

    resp = requests.post(url, json=payload, timeout=30)
    resp.raise_for_status()
    body = resp.json()

    print(f"HTTP {resp.status_code} {resp.reason}")
    print("Response body:")
    print(json.dumps(body, indent=2))
    print()
    return float(body["predictions"][0][0])


def main() -> int:
    write = "--write" in sys.argv

    print("\nMERIDIAN SENTINEL — single transaction walkthrough")
    print(f"Customer {CUSTOMER_ID}: 4 ordinary payments today, then a $50.00 '50 Dollar Pass Check'.\n")

    txns = build_session()
    attach_history(txns)
    target = txns[-1]

    base_url = _env_value("LSTM_SERVING_URL", "http://localhost:8080")
    client = LSTMInferenceClient(base_url, timeout=30)
    if not client.health_check():
        print(f"[!] LSTM inference API not reachable at {base_url}")
        print("    Start the stack first: docker compose up -d")
        return 1

    # --- Step 1: feature engineering -----------------------------------------
    print("=" * 78)
    print("STEP 1 — Feature engineering (compute_feature_matrix, 13 trained features)")
    print("=" * 78)
    import numpy as np
    import pandas as pd
    from src.pipeline.feature_engineering import FEATURE_COLS, SEQ_LEN, compute_feature_matrix

    frame = pd.DataFrame([t.paysim_row() for t in txns])
    frame["_idx"] = range(len(txns))
    features, ordered = compute_feature_matrix(frame, fit=False)

    windows = np.zeros((len(ordered), SEQ_LEN, features.shape[1]), dtype=np.float32)
    for _, group in ordered.groupby("nameOrig"):
        positions = group.index.to_numpy()
        for k, pos in enumerate(positions):
            start = max(0, k - SEQ_LEN + 1)
            seq = features[positions[start: k + 1]]
            windows[pos, SEQ_LEN - len(seq):] = seq

    target_pos = int(ordered[ordered["_idx"] == len(txns) - 1].index[0])
    target_window = windows[target_pos]

    print(f"Window shape fed to the model: {target_window.shape}  (5 transactions x 13 features)")
    print(f"Feature order: {FEATURE_COLS}")
    print("Row 5 (this $50 transaction's own engineered features, MinMax-scaled 0-1):")
    for name, val in zip(FEATURE_COLS, target_window[-1]):
        print(f"    {name:<28} {val:.4f}")
    print()

    # --- Step 2: raw LSTM API call -------------------------------------------
    lstm_score = show_raw_api_call(target_window, base_url)
    target.lstm_score = round(lstm_score, 4)
    target.lstm_source = "model"

    # --- Step 3: SIEM rules ---------------------------------------------------
    print("=" * 78)
    print("STEP 3 — SIEM rule engine (ElasticSIEMCorrelator)")
    print("=" * 78)
    correlator = ElasticSIEMCorrelator()
    siem = correlator.evaluate(target.event())
    target.siem = siem
    for rule in siem["rules"]:
        mark = "TRIGGERED" if rule["triggered"] else "pass"
        print(f"  {rule['rule_id']}  [{mark:>9}]  severity={rule['severity']}")
    print(f"  siem_score = {siem['siem_score']:.4f}\n")

    # --- Step 4: hybrid scorer + step 5 playbook -----------------------------
    print("=" * 78)
    print("STEP 4 — Hybrid threat scorer  (threat_score = lstm*0.60 + siem*0.40)")
    print("=" * 78)

    es = None
    playbook = None
    if write:
        es = _build_es()
        if not es.ping():
            print("[!] Elasticsearch not reachable — cannot --write. Run: docker compose up -d")
            return 1
        playbook = PlaybookEngine(es_client=es)

    scorer = HybridThreatScorer(playbook_engine=playbook)
    result = scorer.score(target.lstm_score, siem, target.event())
    target.result = result

    print(f"  lstm_score   = {target.lstm_score:.4f}")
    print(f"  siem_score   = {siem['siem_score']:.4f}")
    print(f"  threat_score = {target.lstm_score:.4f} * 0.60 + {siem['siem_score']:.4f} * 0.40 "
          f"= {result['threat_score']:.4f}")
    print(f"  verdict      = {result['verdict']}  (trigger_reason={result['trigger_reason']})")
    if result["verdict"] == "FLAGGED":
        print("  -> STEP 5: Playbook fired for real — account locked, incident case opened,")
        print("     analyst notification sent." if write else
              "     (playbook engine not attached in dry-run — re-run with --write to fire it)")
    print()

    # --- Step 6: index to Elasticsearch ---------------------------------------
    if write:
        index = f"meridian-transactions-{datetime.now(tz=timezone.utc):%Y.%m.%d}"
        for t in txns[:-1]:
            es.index(index=index, document=transaction_doc(t), refresh=False)
        es.index(index=index, document=transaction_doc(target), refresh=True)
        print("=" * 78)
        print("STEP 6 — Indexed to Elasticsearch")
        print("=" * 78)
        print(f"  Index: {index}")
        print(f"  Customer: {CUSTOMER_ID}  ({len(txns)} transactions written)\n")

    # --- URLs for screenshots ---------------------------------------------------
    print("=" * 78)
    print("URLS FOR SCREENSHOTS")
    print("=" * 78)
    print(f"  LSTM API status         http://localhost:8080/v1/models/lstm")
    print(f"  LSTM API Swagger UI     http://localhost:8080/docs")
    print(f"                          -> POST /v1/models/lstm:predict, 'Try it out', paste the")
    print(f"                             request body printed under STEP 2 above")
    if write:
        print(f"  React dashboard         http://localhost:5173")
        print(f"                          -> Transaction Feed shows {CUSTOMER_ID}'s $50.00")
        print(f"                             '50 Dollar Pass Check' payment as the newest row")
        print(f"  Kibana Discover         http://localhost:5601/app/discover")
        print(f"                          -> data view 'meridian-transactions-*', search:")
        print(f"                             customer_id:\"{CUSTOMER_ID}\"")
        print(f"  Kibana Dev Tools        http://localhost:5601/app/dev_tools#/console")
        print(f"                          -> GET meridian-transactions-*/_search")
        print(f"                             {{ \"query\": {{ \"match\": {{ \"customer_id\": \"{CUSTOMER_ID}\" }} }} }}")
        print(f"  Kibana Dashboard        http://localhost:5601/app/dashboards")
        print(f"                          -> 'Meridian Sentinel — Fraud Detection Overview'")
        print(f"                             (Stack Management -> Saved Objects -> Import")
        print(f"                             kibana/meridian_overview.ndjson if not already done)")
        print(f"  Elasticsearch (raw)     http://localhost:9200/meridian-transactions-*/_search"
              f"?q=customer_id:%22{CUSTOMER_ID}%22&pretty")
        print(f"                          -> browser will prompt for elastic / $ELASTIC_PASSWORD")
    else:
        print("\n  Nothing was written. Re-run with --write to index it and get live dashboard/Kibana URLs.")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
