"""Follow one fraudulent transaction through the real pipeline, end to end.

The FAIL counterpart to fifty_dollar_pass_check.py. Where that script proves
an ordinary $50 payment sails through clean, this one proves the reverse:
a transaction shaped like real fraud — draining almost the whole balance in
a TRANSFER to a watchlisted mule merchant, after an impossible jump between
cities, outside business hours — gets caught by the real pipeline.

Nothing about the verdict is scripted. The four SIEM rules
(ElasticSIEMCorrelator), the served LSTM, the HybridThreatScorer and the
PlaybookEngine are the exact same real components fifty_dollar_pass_check.py
uses; only the *shape* of the transaction is chosen to look like fraud —
large amount, watchlisted destination, geo-velocity, off-hours, a drained
origin balance and a mule-like destination (money in, mostly straight back
out). If the real model and rules didn't agree, this script would print
whatever they actually decided, not a forced FLAGGED result.

  1. Feature engineering  -> compute_feature_matrix (13 trained features, MinMax-scaled)
  2. LSTM inference       -> the served ONNX model, over a raw HTTP call this
                             script prints in full (request + response)
  3. SIEM rule engine     -> ElasticSIEMCorrelator, every rule's verdict printed
  4. Hybrid scorer        -> HybridThreatScorer (lstm*0.60 + siem*0.40)
  5. Playbook             -> fires for real when the blended score crosses 0.70
                             — account lock, incident case, analyst notification
  6. Elasticsearch        -> the whole session is indexed (with --write), so
                             Kibana and the React dashboard show it live

Dry run (default) evaluates and prints everything, writes nothing::

    docker compose --profile dev run --rm dev python -m scripts.fraud_transaction_fail_check

Live — indexes to Elasticsearch and fires the real playbook if flagged::

    docker compose --profile dev run --rm -e ELASTIC_HOST=http://elasticsearch:9200 dev python -m scripts.fraud_transaction_fail_check --write
"""

from __future__ import annotations

import json
import logging
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
    Txn,
    _build_es,
    _env_value,
    transaction_doc,
)
from src.inference_client import LSTMInferenceClient  # noqa: E402

logging.disable(logging.CRITICAL)

SYDNEY_TZ = ZoneInfo("Australia/Sydney")
CUSTOMER_ID = "CUST-24417"
ORIGIN = "Sydney, NSW"
DESTINATION = "Perth, WA"
WATCHLIST_MERCHANT = ("M7891", "Anon Prepaid Reload", 6540, "Stored Value")


def _target_time(now: datetime) -> datetime:
    """The most recent genuinely off-hours moment (before 08:00 or at/after
    22:00 Sydney local) at or before `now` — never a lied-about clock. If
    it's already off-hours right now, that moment is now itself."""
    sydney_now = now.astimezone(SYDNEY_TZ)
    if sydney_now.hour < 8 or sydney_now.hour >= 22:
        return now
    anchor = (sydney_now - timedelta(days=1)).replace(
        hour=22, minute=15, second=0, microsecond=0
    )
    return anchor.astimezone(timezone.utc)


def build_session() -> list[Txn]:
    """Four ordinary Sydney payments, then a draining TRANSFER to a
    watchlisted merchant in Perth, minutes later, off-hours."""
    now = datetime.now(tz=timezone.utc)
    target_when = _target_time(now)

    prior = [
        ("M0102", "Woolworths", 5411, "Grocery Stores", 62.40, timedelta(hours=11)),
        ("M0105", "BP Service Station", 5541, "Service Stations", 45.00, timedelta(hours=6, minutes=30)),
        ("M0113", "Priceline Pharmacy", 5912, "Drug Stores", 33.80, timedelta(hours=4)),
        ("M0107", "JB Hi-Fi", 5732, "Electronics", 189.00, timedelta(minutes=25)),
    ]

    txns: list[Txn] = []
    balance = 18_500.00
    prev_when = target_when  # overwritten by the loop; kept for the final gap

    for merchant_id, name, mcc, mcc_label, amount, before_target in prior:
        when = target_when - before_target
        old_bal = balance
        new_bal = round(old_bal - amount, 2)
        txns.append(Txn(
            customer_id=CUSTOMER_ID, amount=amount,
            merchant=(merchant_id, name, mcc, mcc_label),
            location=ORIGIN, prev_location=ORIGIN,
            when=when, prev_when=when - timedelta(hours=1),
            channel="Card", txn_type="PAYMENT",
            profile="routine", intent="ordinary payment",
            old_balance_orig=old_bal, new_balance_orig=new_bal,
            old_balance_dest=round(old_bal * 0.3, 2),
            new_balance_dest=round(old_bal * 0.3 + amount, 2),
            is_fraud=0,
        ))
        balance = new_bal
        prev_when = when

    # -- The target: draining transfer to a watchlisted mule account, Perth,
    #    25 minutes after the last Sydney payment, off-hours. --------------
    old_bal = balance
    # A full wipeout, not a partial drain: balance_drop_to_zero requires
    # newbalanceOrig < $1, and amount_to_balance_ratio is strongest at
    # exactly 1.0 — both are among the three strongest trained signals
    # (src/pipeline/feature_engineering.py), so the transaction should
    # actually hit them, not just gesture at "mostly drained."
    drain_amount = old_bal
    new_bal = 0.00
    old_bal_dest = 9_400.00
    target = Txn(
        customer_id=CUSTOMER_ID, amount=drain_amount,
        merchant=WATCHLIST_MERCHANT,
        location=DESTINATION, prev_location=ORIGIN,
        when=target_when, prev_when=prev_when,
        channel="Online", txn_type="TRANSFER",
        profile="attack",
        intent="coordinated attack — draining transfer to a watchlisted mule account",
        old_balance_orig=old_bal, new_balance_orig=new_bal,
        old_balance_dest=old_bal_dest,
        # Mule pattern: money arrives and is mostly moved straight back out —
        # the destination's balance barely reflects what it just received.
        new_balance_dest=round(old_bal_dest + drain_amount * 0.07, 2),
        is_fraud=1,
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

    print("\nMERIDIAN SENTINEL — fraud transaction walkthrough")
    print(f"Customer {CUSTOMER_ID}: 4 ordinary Sydney payments, then a draining TRANSFER")
    print(f"to a watchlisted mule account in Perth, 25 minutes later, off-hours.\n")

    txns = build_session()
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
    print("Row 5 (this transaction's own engineered features, MinMax-scaled 0-1):")
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
    else:
        print("  -> Not flagged by the real pipeline. This is genuinely what the model and")
        print("     rules decided for this input — not a forced result. Re-run to see if a")
        print("     fresh off-hours/geo-velocity draw crosses the line, or inspect the scores")
        print("     above to see how close it came.")
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
        print(f"                          -> Alert queue / Investigate drawer for {CUSTOMER_ID}")
        print(f"                             if the case was flagged")
        print(f"  Kibana Discover         http://localhost:5601/app/discover")
        print(f"                          -> data view 'meridian-transactions-*', search:")
        print(f"                             customer_id:\"{CUSTOMER_ID}\"")
        print(f"  Kibana Dev Tools        http://localhost:5601/app/dev_tools#/console")
        print(f"                          -> GET meridian-incidents-*/_search")
        print(f"                             {{ \"query\": {{ \"match\": {{ \"customer_id\": \"{CUSTOMER_ID}\" }} }} }}")
        print(f"  Elasticsearch (raw)     http://localhost:9200/meridian-transactions-*/_search"
              f"?q=customer_id:%22{CUSTOMER_ID}%22&pretty")
        print(f"                          -> browser will prompt for elastic / $ELASTIC_PASSWORD")
    else:
        print("\n  Nothing was written. Re-run with --write to index it, fire the real playbook")
        print("  if it flags, and get live dashboard/Kibana URLs.")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
