"""Follow a slow-burn fraud run through the real pipeline, end to end.

The third walkthrough, alongside ``fifty_dollar_pass_check.py`` (legitimate)
and ``fraud_transaction_fail_check.py`` (obvious fraud). This one is the case
both of those miss: a customer's card is used for a run of small, ordinary
looking purchases that individually clear every single-transaction rule, but
together take a fifth of the balance inside two hours.

Why this is a rule and not a model prediction
---------------------------------------------
The LSTM cannot detect this pattern, and it is worth being precise about why.
PaySim — the only dataset this project trains on — contains 6,353,307 unique
customers across 6,362,620 transactions: a mean of 1.001 transactions each,
and a maximum of 3 in the entire file. Every labelled fraud case in it is a
single isolated transaction. 99.96% of the training windows the model ever
saw were one real transaction padded with four rows of zeros.

A slow burn is by definition a multi-transaction shape, so there is nothing in
the training data that could teach it. Detecting it with the model would mean
fabricating both the sequences and their fraud labels, which is a different
claim than "the model learned this". SIEM Rule 5 (``_rule_burst_velocity`` in
``src/siem/rule_engine.py``) does it deterministically instead: count the
transactions in a 2-hour window, add up what they took, compare against the
balance the customer started with. No training, no fabricated labels, and the
evidence it emits is something an analyst can check by hand.

Expect MONITOR, not FLAGGED
---------------------------
One triggered rule is a siem_score of 0.33, which contributes 0.33 x 0.40 =
0.132 to the blended threat score — below the 0.70 line. That is the designed
behaviour, not a shortfall: SIEM alone tops out at 0.40 and can never flag a
case by itself. Locking a customer's account because they made six purchases
in an afternoon would be a bad false positive. The rule's job here is to put
the pattern in front of an analyst with its evidence attached.

Dry run (default) evaluates and prints everything, writes nothing::

    docker compose --profile dev run --rm dev python -m scripts.slow_burn_check

Live — indexes to Elasticsearch so the dashboard and Kibana show it::

    docker compose --profile dev run --rm \
        -e ELASTIC_HOST=http://elasticsearch:9200 \
        dev python -m scripts.slow_burn_check --write
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.siem.hybrid_scorer import HybridThreatScorer  # noqa: E402
from src.siem.playbook_engine import PlaybookEngine  # noqa: E402
from src.siem.rule_engine import ElasticSIEMCorrelator  # noqa: E402

from scripts.generate_transaction_batch import (  # noqa: E402
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
CUSTOMER_ID = "CUST-18656"
OPENING_BALANCE = 3_200.00

# The documented CUST-18656 run: six purchases, 15 minutes apart, alternating
# between electronics and restaurants around Darwin. Amounts are the scenario's
# own. Every one of them is small, in business hours, locally plausible, and at
# a merchant nobody has watchlisted — which is the whole point.
BURN_SEQUENCE: list[tuple[str, str, int, str, float]] = [
    ("M0107", "Harvey Norman Darwin", 5732, "Electronics Stores", 256.74),
    ("M0110", "Darwin Noodle House", 5812, "Restaurants", 71.28),
    ("M0107", "JB Hi-Fi Darwin", 5732, "Electronics Stores", 61.59),
    ("M0110", "Hanuman Restaurant", 5812, "Restaurants", 69.46),
    ("M0107", "Harvey Norman Darwin", 5732, "Electronics Stores", 59.53),
    ("M0107", "JB Hi-Fi Darwin", 5732, "Electronics Stores", 146.60),
]


def _last_business_hours_end(now: datetime) -> datetime:
    """The most recent moment that is genuinely inside 08:00-22:00 Sydney time.

    The documented scenario is an afternoon run in which every single-transaction
    rule passes — including Rule 3, off-hours. Running the demo at 3am would
    trip Rule 3 on all six payments and bury the point. Rather than relabel the
    clock, this searches backwards for a real business-hours moment, the same
    way ``_off_hours_slot`` in generate_transaction_batch.py searches for a real
    off-hours one.
    """
    candidate = now
    for _ in range(48):
        if 8 <= candidate.astimezone(SYDNEY_TZ).hour < 22:
            return candidate
        candidate -= timedelta(hours=1)
    return now


def build_session() -> list[Txn]:
    """Two ordinary payments earlier in the day, then the six-payment burst.

    The prior pair does two jobs. It gives the customer an established normal
    pattern for the burst to stand out against, and it fills the LSTM's
    5-transaction window with real rows — a window of pure zero-padding is
    something the model scores erratically (see the walkthrough's notes on
    PaySim's single-transaction customers), and that artifact would otherwise
    show up as a spurious score on the first payment.
    """
    now = _last_business_hours_end(datetime.now(tz=timezone.utc))
    start = now - timedelta(minutes=15 * (len(BURN_SEQUENCE) - 1))

    txns: list[Txn] = []
    balance = OPENING_BALANCE + 118.40  # covers the two earlier payments

    # -- Ordinary earlier activity, well outside the 2-hour burst window ------
    prev_when = start - timedelta(hours=7)
    for j, (mid, mname, mcc, mlabel, amount, hours_before) in enumerate([
        ("M0101", "Coles Darwin", 5411, "Grocery Stores", 84.20, 6.0),
        ("M0115", "The Coffee Club", 5814, "Cafes", 34.20, 4.5),
    ]):
        when = start - timedelta(hours=hours_before)
        old_bal = balance
        new_bal = round(old_bal - amount, 2)
        txns.append(Txn(
            customer_id=CUSTOMER_ID, amount=amount,
            merchant=(mid, mname, mcc, mlabel),
            location="Darwin, NT", prev_location="Darwin, NT",
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

    # -- The burst -----------------------------------------------------------
    for i, (mid, mname, mcc, mlabel, amount) in enumerate(BURN_SEQUENCE):
        when = start + timedelta(minutes=15 * i)
        old_bal = balance
        new_bal = round(old_bal - amount, 2)
        txns.append(Txn(
            customer_id=CUSTOMER_ID, amount=amount,
            merchant=(mid, mname, mcc, mlabel),
            location="Darwin, NT", prev_location="Darwin, NT",
            when=when, prev_when=prev_when,
            channel="Card" if i % 2 == 0 else "Online", txn_type="PAYMENT",
            profile="slow_burn", intent="slow burn - small payments draining the balance",
            old_balance_orig=old_bal, new_balance_orig=new_bal,
            old_balance_dest=round(old_bal * 0.3, 2),
            new_balance_dest=round(old_bal * 0.3 + amount, 2),
            is_fraud=1,
        ))
        balance = new_bal
        prev_when = when

    return txns


def main() -> int:
    write = "--write" in sys.argv

    print("\nMERIDIAN SENTINEL - slow burn walkthrough")
    print(f"Customer {CUSTOMER_ID}: {len(BURN_SEQUENCE)} small Darwin payments over "
          f"{15 * (len(BURN_SEQUENCE) - 1)} minutes,")
    print(f"opening balance A${OPENING_BALANCE:,.2f}. No single payment breaks a rule.\n")

    txns = build_session()
    attach_history(txns)

    base_url = _env_value("LSTM_SERVING_URL", "http://localhost:8080")
    client = LSTMInferenceClient(base_url, timeout=30)
    if not client.health_check():
        print(f"[!] LSTM inference API not reachable at {base_url}")
        print("    Start the stack first: docker compose up -d")
        return 1

    scored, why = score_with_model(txns, client)
    if not scored:
        print(f"[!] Model scoring failed: {why}")
        return 1

    es = None
    playbook = None
    if write:
        es = _build_es()
        if not es.ping():
            print("[!] Elasticsearch not reachable - cannot --write. Run: docker compose up -d")
            return 1
        playbook = PlaybookEngine(es_client=es)

    correlator = ElasticSIEMCorrelator()
    scorer = HybridThreatScorer(playbook_engine=playbook)

    print("=" * 92)
    print("THE RUN - each payment scored by the real pipeline as it arrives")
    print("=" * 92)
    header = (f"{'#':>2}  {'time':<6} {'merchant':<22} {'amount':>9}  "
              f"{'rules fired':<12} {'beh':>5} {'risk':>5}  verdict")
    print(header)
    print("-" * len(header))

    for i, txn in enumerate(txns, start=1):
        txn.siem = correlator.evaluate(txn.event())
        txn.result = scorer.score(txn.lstm_score, txn.siem, txn.event())
        fired = [r["rule_id"].replace("RULE_00", "R") for r in txn.siem["rules"] if r["triggered"]]
        local = txn.when.astimezone(SYDNEY_TZ)
        print(f"{i:>2}  {local:%H:%M}  {txn.merchant[1]:<22} ${txn.amount:>8.2f}  "
              f"{','.join(fired) or 'none':<12} {txn.lstm_score:>5.2f} "
              f"{txn.result['threat_score']:>5.2f}  {txn.result['verdict']}")

    final = txns[-1]
    burst = next(r for r in final.siem["rules"] if r["rule_id"] == "RULE_005")
    ev = burst["evidence"]

    print("\n" + "=" * 92)
    print("RULE 5 - burst velocity, evaluated on the final payment")
    print("=" * 92)
    if "error" in ev:
        print(f"  could not evaluate: {ev['error']}")
    else:
        print(f"  transactions in the last {ev['window_minutes']} min : "
              f"{ev['transaction_count']}  (threshold {ev['threshold_count']})")
        print(f"  taken from the balance                : "
              f"A${ev['cumulative_amount']:,.2f} of A${ev['balance_before']:,.2f}")
        print(f"  fraction of balance drained           : "
              f"{ev['balance_fraction']:.2%}  (threshold {ev['threshold_fraction']:.0%})")
        print(f"  triggered                             : {burst['triggered']}")

    print("\n" + "=" * 92)
    print("WHY THIS IS MONITOR AND NOT FLAGGED")
    print("=" * 92)
    fired_final = [r["rule_id"] for r in final.siem["rules"] if r["triggered"]]
    print(f"  behaviour (LSTM) : {final.lstm_score:.4f}   the model has no multi-transaction")
    print("                              training data, so it has nothing to say here")
    print(f"  rules (SIEM)     : {final.siem['siem_score']:.2f}     "
          f"{len(fired_final)} rule(s) triggered: {', '.join(fired_final) or 'none'}")
    print(f"  blended          : {final.result['threat_score']:.4f}   "
          f"= {final.lstm_score:.4f} x 0.60 + {final.siem['siem_score']:.2f} x 0.40")
    print("  SIEM on its own tops out at 0.40, below the 0.70 flag line. The pattern is")
    print("  surfaced for an analyst with its evidence attached, not auto-contained -")
    print("  locking an account over six afternoon purchases would be a bad call.")

    if write:
        index = f"meridian-transactions-{datetime.now(tz=timezone.utc):%Y.%m.%d}"
        for txn in txns[:-1]:
            es.index(index=index, document=transaction_doc(txn), refresh=False)
        es.index(index=index, document=transaction_doc(final), refresh=True)
        print("\n" + "=" * 92)
        print("INDEXED TO ELASTICSEARCH")
        print("=" * 92)
        print(f"  Index    : {index}")
        print(f"  Customer : {CUSTOMER_ID}  ({len(txns)} transactions written)")
        print("  Dashboard: http://localhost:5173")
        print(f"  Kibana   : http://localhost:5601/app/discover  ->  "
              f"customer_id:\"{CUSTOMER_ID}\"")
    else:
        print("\n  Nothing was written. Re-run with --write to index it.")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
