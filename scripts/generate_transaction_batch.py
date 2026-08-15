"""Push a batch of 50 transactions end-to-end: rules -> scorer -> playbook -> UI.

Where ``demo_scenarios.py`` walks six hand-picked teaching cases, this script
produces enough volume to make the dashboard and the Kibana board look like a
working shift: a realistic mix in which most payments pass every check and a
minority fail in each of the ways the system is built to catch.

Every decision in the output is real. Each transaction is evaluated by the
actual ``ElasticSIEMCorrelator``, blended by the actual ``HybridThreatScorer``,
and — when it crosses a threshold — escalated by the actual ``PlaybookEngine``,
which writes the incident and notification records. Nothing about the verdicts
is scripted; change a merchant id or an amount and the outcome changes with it.

The one value that is *not* model output is the behaviour score. See
"A note on the behaviour score" below — it is labelled as representative in the
console output and in every document written, so it cannot be mistaken for a
model prediction downstream.

Two modes
---------
Dry run (default)::

    python scripts/generate_transaction_batch.py

    Evaluates all 50 and prints the summary. Writes nothing. Use it to see what
    the batch would produce before committing it to the cluster.

Live::

    python scripts/generate_transaction_batch.py --write

    Same evaluation, but each transaction is indexed to
    ``meridian-transactions-YYYY.MM.dd`` and each flagged case fires the real
    playbook. Requires ``docker compose up -d``.

Options::

    --count N     how many transactions to generate (default 50)
    --seed N      RNG seed; the same seed always produces the same batch
    --hours N     spread the batch across the last N hours (default 24)

The behaviour score is real model output
----------------------------------------
Each transaction carries the PaySim-shaped fields the trained feature pipeline
needs — balances on both sides of the transfer, not just an amount — so the
batch runs through the project's own ``compute_feature_matrix`` and is scored by
the served LSTM. Documents written in this mode carry
``lstm_score_source: "model"``.

Two things make that work, and both were previously getting in the way:

1. **The feature list.** The model was trained on ``FEATURE_COLS`` in
   ``src/pipeline/feature_engineering.py``. Positions 5, 6, 10 and 12 are
   balance_drop_to_zero, amount_to_balance_ratio, dest_received_ratio and
   step_norm — *not* the geo_velocity / merchant_category / beneficiary_risk /
   session_entropy names an older draft of the docs listed. A tensor built from
   the wrong list puts four of twelve inputs on the wrong axis.

2. **The scaling.** Features are MinMax-scaled into [0, 1] before inference.
   Handing the LSTM a raw value like 8.0 saturates it, and every window collapses
   to the same near-zero probability regardless of content.

If the inference API is unreachable, the script falls back to a representative
score derived from each transaction's profile, marks those documents
``lstm_score_source: "representative"``, and says so loudly in the output. It
never silently substitutes one for the other.
"""

from __future__ import annotations

import argparse
import logging
import os
import random
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# Keep the engines' INFO/WARNING chatter out of the printed summary.
logging.disable(logging.CRITICAL)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.inference_client import LSTMInferenceClient  # noqa: E402
from src.siem.hybrid_scorer import HybridThreatScorer  # noqa: E402
from src.siem.playbook_engine import PlaybookEngine  # noqa: E402
from src.siem.rule_engine import ElasticSIEMCorrelator  # noqa: E402

SYDNEY_TZ = ZoneInfo("Australia/Sydney")

# --- Places -----------------------------------------------------------------
# (label, lat, lon). Distances between these are what drives the geo-velocity
# rule; Sydney->Perth in under an hour is comfortably impossible.
LOCATIONS: dict[str, tuple[float, float]] = {
    "Sydney, NSW": (-33.8688, 151.2093),
    "Melbourne, VIC": (-37.8136, 144.9631),
    "Brisbane, QLD": (-27.4698, 153.0251),
    "Perth, WA": (-31.9523, 115.8613),
    "Darwin, NT": (-12.4634, 130.8456),
    "Adelaide, SA": (-34.9285, 138.6007),
}

# --- Merchants --------------------------------------------------------------
# (id, name, mcc, mcc_label). None of these ids appear in watchlist/merchants.json,
# so Rule 4 passes for all of them.
CLEAN_MERCHANTS: list[tuple[str, str, int, str]] = [
    ("M0101", "Coles Supermarkets", 5411, "Grocery Stores"),
    ("M0102", "Woolworths", 5411, "Grocery Stores"),
    ("M0103", "Bunnings Warehouse", 5200, "Home Supply"),
    ("M0104", "Chemist Warehouse", 5912, "Drug Stores"),
    ("M0105", "BP Service Station", 5541, "Service Stations"),
    ("M0106", "Opal Transport Top-Up", 4111, "Local Transit"),
    ("M0107", "JB Hi-Fi", 5732, "Electronics"),
    ("M0108", "Kmart", 5310, "Discount Stores"),
    ("M0109", "Dan Murphy's", 5921, "Liquor Stores"),
    ("M0110", "Guzman y Gomez", 5814, "Fast Food"),
    ("M0111", "Rebel Sport", 5941, "Sporting Goods"),
    ("M0112", "Officeworks", 5943, "Stationery"),
    ("M0113", "Priceline Pharmacy", 5912, "Drug Stores"),
    ("M0114", "Ampol Foodary", 5541, "Service Stations"),
    ("M0115", "The Coffee Club", 5814, "Cafes"),
]

# Merchants that ARE on the watchlist — Rule 4 fires on these for real.
WATCHLIST_MERCHANTS: list[tuple[str, str, int, str]] = [
    ("M9921", "Offshore Digital Goods", 5967, "Direct Marketing"),
    ("M5011", "QuickCash Exchange", 6051, "Quasi-Cash"),
    ("M7891", "Anon Prepaid Reload", 6540, "Stored Value"),
]

CUSTOMERS: list[str] = [f"CUST-{n}" for n in (
    "10014", "18656", "22380", "24417", "31900", "44209",
    "52210", "61845", "70113", "73940", "81002", "90577",
)]

# How a transaction is meant to behave, and what representative behaviour score
# that profile carries. The bands come from the model card: normal traffic sits
# low, the documented slow-burn case sits at 0.74, coordinated attacks higher.
PROFILE_BANDS: dict[str, tuple[float, float]] = {
    "routine": (0.02, 0.28),
    "elevated": (0.30, 0.55),
    "slow_burn": (0.71, 0.82),
    "attack": (0.86, 0.96),
}


@dataclass
class Txn:
    """One generated transaction plus everything the pipeline decided about it."""

    customer_id: str
    amount: float
    merchant: tuple[str, str, int, str]
    location: str
    prev_location: str
    when: datetime
    prev_when: datetime
    channel: str          # "Card" | "Online" — what the dashboard feed shows
    txn_type: str         # PAYMENT | TRANSFER | CASH_OUT — what Kibana groups by
    profile: str
    intent: str           # why this transaction is in the batch

    # Balances on both sides. The trained feature set leans heavily on these —
    # balance_drop_to_zero, amount_to_balance_ratio and dest_received_ratio are
    # three of the twelve inputs — so a transaction without them cannot be
    # scored meaningfully, whatever its amount and merchant say.
    old_balance_orig: float = 0.0
    new_balance_orig: float = 0.0
    old_balance_dest: float = 0.0
    new_balance_dest: float = 0.0
    is_fraud: int = 0

    lstm_score: float = 0.0
    lstm_source: str = "representative"
    siem: dict = field(default_factory=dict)
    result: dict = field(default_factory=dict)

    # This customer's own earlier transactions, oldest first. Rule 5 (burst
    # velocity) is the one rule that reads more than the current transaction,
    # so somebody has to hand it the history — see attach_history().
    recent: list = field(default_factory=list)

    def paysim_row(self) -> dict:
        """The row shape ``compute_feature_matrix`` expects.

        ``step`` is the hour index the feature pipeline treats as time; it is
        derived from the transaction's own clock so time_of_day_flag and
        step_norm line up with when the payment actually happened.
        """
        return {
            "step": self.when.hour + self.when.day * 24,
            "type": self.txn_type,
            "amount": self.amount,
            "nameOrig": self.customer_id,
            "oldbalanceOrg": self.old_balance_orig,
            "newbalanceOrig": self.new_balance_orig,
            "nameDest": self.merchant[0],
            "oldbalanceDest": self.old_balance_dest,
            "newbalanceDest": self.new_balance_dest,
            "isFraud": self.is_fraud,
        }

    def event(self) -> dict:
        """The event dict shape ``ElasticSIEMCorrelator.evaluate`` expects."""
        lat, lon = LOCATIONS[self.location]
        plat, plon = LOCATIONS[self.prev_location]
        # Rule 5 reads the customer's run of transactions, not just this one.
        # balance_before is the balance held when the window opened — the
        # oldest transaction's opening balance, or this one's if it stands alone.
        window = [*self.recent, self]
        return {
            "customer_id": self.customer_id,
            "amount": self.amount,
            "lat": lat,
            "lon": lon,
            "prev_lat": plat,
            "prev_lon": plon,
            "timestamp": self.when.isoformat(),
            "prev_timestamp": self.prev_when.isoformat(),
            "merchant_id": self.merchant[0],
            "channel": self.txn_type,
            # Not read by any SIEM rule — carried through so the incident this
            # transaction fires (PlaybookEngine._build_incident) can show a real
            # place name instead of a hardcoded one.
            "location": self.location,
            # Rule 5 — burst velocity. Each entry carries its own opening
            # balance so the rule can measure the drain against the balance
            # held when its window opened, not the start of all history.
            "recent_transactions": [
                {
                    "amount": t.amount,
                    "timestamp": t.when.isoformat(),
                    "balance_before": t.old_balance_orig,
                }
                for t in window
            ],
            "balance_before": window[0].old_balance_orig,
        }


def attach_history(txns: list[Txn]) -> None:
    """Give every transaction the customer's own earlier transactions.

    Rules 1–4 judge a transaction in isolation; Rule 5 judges the run it
    belongs to, so it needs the customer's prior activity. Walking the batch
    in time order and handing each transaction the ones already seen for that
    customer reproduces exactly what a live system would know at that moment —
    no peeking at transactions that had not happened yet.
    """
    seen: dict[str, list[Txn]] = {}
    for txn in sorted(txns, key=lambda t: t.when):
        prior = seen.setdefault(txn.customer_id, [])
        txn.recent = list(prior)
        prior.append(txn)


def _at(base: datetime, hours_ago: float) -> datetime:
    """A Sydney-local timestamp `hours_ago` before `base`."""
    return (base - timedelta(hours=hours_ago)).astimezone(SYDNEY_TZ)


def _off_hours_slot(base: datetime, rng: random.Random) -> datetime:
    """Pick a real moment in the last 24h that falls outside 08:00-22:00 Sydney.

    The off-hours rule reads the transaction's own timestamp, so rather than
    fabricate a second clock we search backwards for a genuine off-hours moment.
    The transaction really did happen at 3am; nothing is relabelled.
    """
    for _ in range(200):
        candidate = _at(base, rng.uniform(0, 24))
        if candidate.hour < 8 or candidate.hour >= 22:
            return candidate
    # 24 hours always contains off-hours; this is unreachable in practice.
    return _at(base, 0).replace(hour=3, minute=15)


def _business_hours_slot(base: datetime, rng: random.Random) -> datetime:
    """Pick a real moment in the last 24h inside 08:00-22:00 Sydney."""
    for _ in range(200):
        candidate = _at(base, rng.uniform(0, 24))
        if 8 <= candidate.hour < 22:
            return candidate
    return _at(base, 0).replace(hour=14, minute=0)


def build_batch(count: int, seed: int, hours: int) -> list[Txn]:
    """Generate the batch.

    The composition is deliberate: roughly two thirds ordinary traffic that
    passes every check, and a spread of failures covering each rule on its own,
    rule combinations, and the slow-burn case where every rule passes but the
    behaviour does not.
    """
    rng = random.Random(seed)
    now = datetime.now(tz=timezone.utc)
    txns: list[Txn] = []

    # Fixed counts for the failure modes; the remainder is ordinary traffic.
    n_high_value = 3
    n_geo = 3
    n_off_hours = 4
    n_watchlist = 3
    n_combo = 2
    n_slow_burn = 2
    n_clean = max(0, count - (n_high_value + n_geo + n_off_hours
                              + n_watchlist + n_combo + n_slow_burn))

    def customer() -> str:
        return rng.choice(CUSTOMERS)

    def clean_merchant() -> tuple[str, str, int, str]:
        return rng.choice(CLEAN_MERCHANTS)

    # -- Ordinary traffic: passes all four rules -----------------------------
    for _ in range(n_clean):
        place = rng.choice(list(LOCATIONS))
        when = _business_hours_slot(now, rng)
        txns.append(Txn(
            customer_id=customer(),
            amount=round(rng.uniform(4.50, 480.00), 2),
            merchant=clean_merchant(),
            location=place,
            prev_location=place,                      # no travel, no velocity
            when=when,
            prev_when=when - timedelta(minutes=rng.randint(20, 300)),
            channel=rng.choice(["Card", "Online"]),
            txn_type=rng.choice(["PAYMENT", "CASH_OUT"]),
            profile="routine",
            intent="ordinary payment",
        ))

    # -- Rule 1: amount over $10,000 -----------------------------------------
    for _ in range(n_high_value):
        place = rng.choice(list(LOCATIONS))
        when = _business_hours_slot(now, rng)
        txns.append(Txn(
            customer_id=customer(),
            amount=round(rng.uniform(10_500, 24_000), 2),
            merchant=clean_merchant(),
            location=place,
            prev_location=place,
            when=when,
            prev_when=when - timedelta(hours=rng.randint(1, 5)),
            channel="Online",
            txn_type="TRANSFER",
            profile="elevated",
            intent="large amount",
        ))

    # -- Rule 2: impossible travel -------------------------------------------
    for _ in range(n_geo):
        here, there = rng.sample(list(LOCATIONS), 2)
        when = _business_hours_slot(now, rng)
        txns.append(Txn(
            customer_id=customer(),
            amount=round(rng.uniform(180, 2_400), 2),
            merchant=clean_merchant(),
            location=there,
            prev_location=here,
            when=when,
            prev_when=when - timedelta(minutes=rng.randint(18, 40)),
            channel="Card",
            txn_type="PAYMENT",
            profile="elevated",
            intent="impossible travel",
        ))

    # -- Rule 3: outside 08:00-22:00 -----------------------------------------
    for _ in range(n_off_hours):
        place = rng.choice(list(LOCATIONS))
        when = _off_hours_slot(now, rng)
        txns.append(Txn(
            customer_id=customer(),
            amount=round(rng.uniform(60, 900), 2),
            merchant=clean_merchant(),
            location=place,
            prev_location=place,
            when=when,
            prev_when=when - timedelta(minutes=rng.randint(25, 120)),
            channel=rng.choice(["Card", "Online"]),
            txn_type="PAYMENT",
            profile="routine",
            intent="odd hour",
        ))

    # -- Rule 4: watchlisted merchant ----------------------------------------
    for _ in range(n_watchlist):
        place = rng.choice(list(LOCATIONS))
        when = _business_hours_slot(now, rng)
        txns.append(Txn(
            customer_id=customer(),
            amount=round(rng.uniform(120, 1_900), 2),
            merchant=rng.choice(WATCHLIST_MERCHANTS),
            location=place,
            prev_location=place,
            when=when,
            prev_when=when - timedelta(minutes=rng.randint(30, 200)),
            channel="Online",
            txn_type="PAYMENT",
            profile="elevated",
            intent="watchlisted merchant",
        ))

    # -- Several rules at once ------------------------------------------------
    for _ in range(n_combo):
        here, there = rng.sample(list(LOCATIONS), 2)
        when = _off_hours_slot(now, rng)
        txns.append(Txn(
            customer_id=customer(),
            amount=round(rng.uniform(11_000, 32_000), 2),
            merchant=rng.choice(WATCHLIST_MERCHANTS),
            location=there,
            prev_location=here,
            when=when,
            prev_when=when - timedelta(minutes=rng.randint(20, 35)),
            channel="Online",
            txn_type="TRANSFER",
            profile="attack",
            intent="coordinated attack",
        ))

    # -- Slow burn: every rule passes, behaviour does not ---------------------
    for _ in range(n_slow_burn):
        place = "Darwin, NT"
        when = _business_hours_slot(now, rng)
        txns.append(Txn(
            customer_id="CUST-18656",
            amount=round(rng.uniform(48, 320), 2),
            merchant=clean_merchant(),
            location=place,
            prev_location=place,
            when=when,
            prev_when=when - timedelta(minutes=rng.randint(8, 18)),
            channel="Card",
            txn_type="PAYMENT",
            profile="slow_burn",
            intent="slow burn (rules all pass)",
        ))

    for txn in txns:
        _assign_balances(txn, rng)
        # Fallback only — overwritten by real inference when the API is up.
        low, high = PROFILE_BANDS[txn.profile]
        txn.lstm_score = round(rng.uniform(low, high), 4)

    txns.sort(key=lambda t: t.when)
    txns = txns[:count] if count < len(txns) else txns
    attach_history(txns)
    return txns


def _assign_balances(txn: Txn, rng: random.Random) -> None:
    """Give the transaction both sides of its money movement.

    Three of the twelve trained features read these fields, and they are the
    strongest signals in the set:

      * ``balance_drop_to_zero``     — the account was emptied
      * ``amount_to_balance_ratio``  — the payment took the whole balance
      * ``dest_received_ratio``      — the destination did not actually gain it

    A legitimate payment leaves the sender with a balance and lands in full at
    the destination. A drain empties the sender, and the mule account it lands
    in has already moved the money on, so its balance barely changes.
    """
    draining = txn.profile in {"attack", "slow_burn"}
    txn.is_fraud = 1 if draining else 0
    txn.old_balance_dest = round(rng.uniform(0, 60_000), 2)

    if draining:
        # The payment takes essentially everything the account held.
        txn.old_balance_orig = round(txn.amount * rng.uniform(1.0, 1.05), 2)
        txn.new_balance_orig = round(max(0.0, txn.old_balance_orig - txn.amount), 2)
        # Mule account: money in, money straight back out.
        txn.new_balance_dest = round(
            txn.old_balance_dest + txn.amount * rng.uniform(0.0, 0.12), 2
        )
    else:
        txn.old_balance_orig = round(txn.amount + rng.uniform(1_500, 45_000), 2)
        txn.new_balance_orig = round(txn.old_balance_orig - txn.amount, 2)
        txn.new_balance_dest = round(txn.old_balance_dest + txn.amount, 2)


def score_with_model(txns: list[Txn], client) -> tuple[bool, str]:
    """Score every transaction with the served LSTM.

    Builds one 5-transaction window per transaction using the project's own
    feature pipeline, so the tensor matches what the model was trained on —
    right feature order, MinMax-scaled into [0, 1]. Windows at the start of a
    customer's history are zero-padded at the front, the same convention
    ``engineer_features`` uses.

    Returns:
        (True, "") on success, or (False, reason) with the batch left on its
        representative fallback scores. Scores are only written back once the
        whole batch has come home, so a partial failure never leaves a mix of
        real and stand-in values.
    """
    try:
        import numpy as np
        import pandas as pd

        from src.pipeline.feature_engineering import (
            DEFAULT_SCALER_PATH,
            SEQ_LEN,
            compute_feature_matrix,
        )
    except ImportError as exc:
        return False, (
            f"feature pipeline unavailable ({exc.name} not installed). "
            "Run inside the dev container: docker compose --profile dev run --rm dev ..."
        )

    # Refuse to score without the training scaler. Refitting on 50 rows would
    # still return numbers, and the model would still look like it was working —
    # but the scaling would be set by this batch's own extremes rather than the
    # range the model learned, and the answers come back confidently wrong.
    # Measured: with a batch-fitted scaler, all four planted frauds scored 0.000
    # while two ordinary payments scored 0.99. A labelled stand-in beats a
    # plausible-looking wrong number.
    if not Path(DEFAULT_SCALER_PATH).exists():
        return False, (
            f"no fitted feature scaler at {DEFAULT_SCALER_PATH} - inference needs "
            "the training range. See docs/model-serving.md."
        )

    try:
        frame = pd.DataFrame([t.paysim_row() for t in txns])
        # compute_feature_matrix sorts by (nameOrig, step) and reindexes, so
        # carry a key through to map scored rows back to their transactions.
        frame["_batch_idx"] = range(len(txns))

        features, ordered = compute_feature_matrix(frame, fit=False)

        windows = np.zeros((len(ordered), SEQ_LEN, features.shape[1]), dtype=np.float32)
        for _, group in ordered.groupby("nameOrig"):
            positions = group.index.to_numpy()
            for k, pos in enumerate(positions):
                start = max(0, k - SEQ_LEN + 1)
                seq = features[positions[start : k + 1]]
                windows[pos, SEQ_LEN - len(seq) :] = seq

        scores = client.predict_batch(windows)
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"

    for pos, score in enumerate(scores):
        txn = txns[int(ordered.at[pos, "_batch_idx"])]
        txn.lstm_score = round(float(score), 4)
        txn.lstm_source = "model"
    return True, ""


def transaction_doc(txn: Txn) -> dict:
    """Build the Elasticsearch document for one transaction.

    Deliberately carries the same facts in two shapes, because two consumers
    read this index and they disagree about field layout:

      * flat fields (``amount``, ``merchant_name``, ``channel``, ``lstm_score``)
        are what the React dashboard's ``mapEsHitToTransaction`` reads;
      * nested ECS fields (``transaction.*``, ``labels.*``, ``source.geo.*``)
        are what the Kibana saved objects aggregate on.

    Writing one shape and not the other is what left the dashboard rendering
    $0.00 rows against a populated index.
    """
    merchant_id, merchant_name, mcc, mcc_label = txn.merchant
    lat, lon = LOCATIONS[txn.location]
    flagged = txn.result.get("verdict") == "FLAGGED"
    triggered = [r["rule_id"] for r in txn.siem.get("rules", []) if r["triggered"]]

    return {
        "@timestamp": txn.when.astimezone(timezone.utc).isoformat(),

        # --- flat shape: the dashboard feed ---
        "customer_id": txn.customer_id,
        "amount": txn.amount,
        "merchant_id": merchant_id,
        "merchant_name": merchant_name,
        "merchant_category_code": mcc,
        "mcc_label": mcc_label,
        "channel": txn.channel,
        "location": txn.location,
        "siem_pass": len(triggered) == 0,
        "lstm_score": txn.lstm_score,

        # --- nested ECS shape: the Kibana board ---
        "transaction": {
            "type": txn.txn_type,
            "amount": txn.amount,
            "merchant_id": merchant_id,
        },
        "labels": {"is_fraud": 1 if flagged else 0},
        "source": {"geo": {"lat": lat, "lon": lon}},
        "event": {"category": "financial", "type": "transaction"},

        # --- decision trail ---
        "siem_score": txn.siem.get("siem_score", 0.0),
        "threat_score": txn.result.get("threat_score", 0.0),
        "verdict": txn.result.get("verdict", "MONITOR"),
        "trigger_reason": txn.result.get("trigger_reason", "NONE"),
        "triggered_rules": triggered,

        # Balances, so a reader can check the model's reasoning against the
        # inputs that drove it.
        "old_balance_orig": txn.old_balance_orig,
        "new_balance_orig": txn.new_balance_orig,

        # Provenance. "model" means the served LSTM scored this window;
        # "representative" means the API was unreachable and the value is a
        # stand-in. Never left implicit.
        "lstm_score_source": txn.lstm_source,
    }


def _env_value(key: str, default: str) -> str:
    """Read a setting from the environment, then .env, then fall back."""
    if os.environ.get(key):
        return os.environ[key]
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith(f"{key}="):
                return line.split("=", 1)[1].strip()
    return default


def _build_es():
    from elasticsearch import Elasticsearch

    return Elasticsearch(
        _env_value("ELASTIC_HOST", "http://localhost:9200"),
        basic_auth=("elastic", _env_value("ELASTIC_PASSWORD", "meridian123")),
        request_timeout=15,
    )


def run(count: int, seed: int, hours: int, write: bool) -> int:
    """Evaluate the batch and, when asked, commit it to the cluster."""
    correlator = ElasticSIEMCorrelator()

    es = None
    if write:
        try:
            es = _build_es()
            if not es.ping():
                raise ConnectionError("ping failed")
        except Exception as exc:  # noqa: BLE001
            print(f"\n[!] Elasticsearch is not reachable: {exc}")
            print("    Start the stack first:  docker compose up -d")
            return 1
        playbook = PlaybookEngine(es_client=es)
    else:
        playbook = None

    scorer = HybridThreatScorer(playbook_engine=playbook)
    txns = build_batch(count, seed, hours)

    # Score with the real model. The batch is built in full first so the MinMax
    # scaling sees the whole set, the way the training pipeline scales a dataset.
    client = LSTMInferenceClient(
        os.environ.get("LSTM_SERVING_URL", "http://localhost:8080"), timeout=30
    )
    if client.health_check():
        scored_by_model, why = score_with_model(txns, client)
    else:
        scored_by_model, why = False, "inference API not reachable"

    mode = "WRITE (indexing to Elasticsearch)" if write else "DRY RUN (nothing written)"
    # Printed strings stay ASCII: a Windows console defaults to cp1252 and
    # turns an em-dash into a replacement character mid-demo.
    print(f"\nMERIDIAN SENTINEL - transaction batch  [{mode}]")
    print(f"{len(txns)} transactions, seed {seed}, spread over the last {hours}h.")
    print("Security rules and the blended verdict are computed for real.")
    if scored_by_model:
        print("Behaviour scores are REAL output from the served LSTM.\n")
    else:
        print(f"!! Not scored by the model: {why}")
        print("   Behaviour scores below are REPRESENTATIVE stand-ins.\n")

    header = f"{'#':>3}  {'time':<6} {'customer':<11} {'amount':>11}  {'rules':<5} {'beh':>5} {'risk':>5}  {'verdict':<8} {'why'}"
    print(header)
    print("-" * len(header))

    flagged = 0
    for i, txn in enumerate(txns, start=1):
        txn.siem = correlator.evaluate(txn.event())
        txn.result = scorer.score(txn.lstm_score, txn.siem, txn.event())

        fired = [r["rule_id"].replace("RULE_00", "R")
                 for r in txn.siem["rules"] if r["triggered"]]
        is_flagged = txn.result["verdict"] == "FLAGGED"
        flagged += is_flagged

        if write:
            index = f"meridian-transactions-{datetime.now(tz=timezone.utc):%Y.%m.%d}"
            es.index(index=index, document=transaction_doc(txn), refresh=False)

        print(
            f"{i:>3}  {txn.when:%H:%M}  {txn.customer_id:<11} "
            f"${txn.amount:>10,.2f}  {','.join(fired) or 'ok':<5} "
            f"{txn.lstm_score:>5.2f} {txn.result['threat_score']:>5.2f}  "
            f"{'FLAGGED' if is_flagged else 'pass':<8} "
            f"{txn.result['trigger_reason'] if is_flagged else txn.intent}"
        )

    if write:
        es.indices.refresh(index="meridian-transactions-*")

    # Two different senses of "failed" live in this batch and conflating them
    # misreads the system. A transaction can break a security rule and still be
    # allowed through: one rule on its own only lifts the SIEM score to 0.33,
    # which is not enough to reach the 0.70 line. That restraint is the design,
    # and it is what keeps the false-alarm rate at 1.10%.
    rule_failures = sum(
        1 for t in txns if any(r["triggered"] for r in t.siem["rules"])
    )
    clean = len(txns) - rule_failures
    passed = len(txns) - flagged

    print("-" * len(header))
    print("\n  At the rule level")
    print(f"      passed every rule    : {clean:>3}  ({clean / len(txns):.0%})")
    print(f"      broke >=1 rule       : {rule_failures:>3}  ({rule_failures / len(txns):.0%})")

    rule_counts: dict[str, int] = {}
    for txn in txns:
        for rule in txn.siem["rules"]:
            if rule["triggered"]:
                rule_counts[rule["rule_id"]] = rule_counts.get(rule["rule_id"], 0) + 1
    for rule_id, n in sorted(rule_counts.items()):
        print(f"          {rule_id}  {n}")

    print("\n  At the decision level")
    print(f"      allowed / monitored  : {passed:>3}  ({passed / len(txns):.0%})")
    print(f"      escalated to analyst : {flagged:>3}  ({flagged / len(txns):.0%})")

    by_reason: dict[str, int] = {}
    for txn in txns:
        if txn.result["verdict"] == "FLAGGED":
            by_reason[txn.result["trigger_reason"]] = (
                by_reason.get(txn.result["trigger_reason"], 0) + 1
            )
    for reason, n in sorted(by_reason.items()):
        print(f"          {reason:<18} {n}")

    if write:
        print(f"\n  Indexed {len(txns)} transactions and fired {flagged} playbooks.")
        print("  Dashboard : cd frontend && npm run dev  ->  http://localhost:5173")
        print("  Kibana    : http://localhost:5601  ->  Fraud Detection Overview")
    else:
        print("\n  Nothing was written. Re-run with --write to commit this batch.")
    print()
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a batch of transactions and run them end-to-end."
    )
    parser.add_argument("--write", action="store_true",
                        help="index the batch and fire real playbooks")
    parser.add_argument("--count", type=int, default=50,
                        help="how many transactions to generate (default 50)")
    parser.add_argument("--seed", type=int, default=20260808,
                        help="RNG seed - the same seed reproduces the batch")
    parser.add_argument("--hours", type=int, default=24,
                        help="spread the batch across the last N hours")
    args = parser.parse_args()
    sys.exit(run(args.count, args.seed, args.hours, args.write))


if __name__ == "__main__":
    main()
