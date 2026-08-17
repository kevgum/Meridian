"""Continuously simulate real-world transaction flow against the live stack.

Where ``generate_transaction_batch.py`` produces one fixed-size batch,
``live_stream.py`` runs forever (or for ``--duration`` seconds), emitting one
transaction at a time at a randomised, human-scale interval -- the way a real
banking channel actually arrives, not a nightly file drop.

Nothing about a customer's story is hand-assigned per tick. Each simulated
customer carries a running balance and a last-known location across the
session, and this tick's transaction is built from THAT state -- so an
impossible-travel case (Rule 2) is a real consequence of "this customer's
previous transaction, seconds ago, was in a different city," not a scenario
picked to look like one. The one exception is off-hours (Rule 3): the
transaction's timestamp is always the real wall clock, so that rule only
fires when it is genuinely outside 08:00-22:00 Sydney time right now. A
simulator that lies about its own clock to force a rule isn't simulating
anything.

Requires the full stack: Elasticsearch to write to, the LSTM inference API for
real behaviour scores. There is no representative-score fallback and no
dry-run mode here -- if either service is unreachable the script refuses to
start. ``generate_transaction_batch.py`` already establishes the policy this
follows: a labelled stand-in beats a plausible-looking wrong number. Here that
means refusing to open a "live" stream that secretly isn't.

Usage::

    docker compose --profile dev run --rm dev python -m scripts.live_stream

    Ctrl+C stops it cleanly and prints a session summary.

Options::

    --interval-min / --interval-max  seconds between transactions (default 2-8)
    --duration N                     stop automatically after N seconds (default: run forever)
    --max-history N                  transactions kept in memory for feature
                                      computation (default 300 -- see note below)
    --seed N                         RNG seed for the profile/customer/amount
                                      draw (timestamps are always real time)

Why --max-history exists
-------------------------
Every tick is scored by handing the *entire* accumulated in-memory history to
``score_with_model`` -- the exact function ``generate_transaction_batch.py``
uses, so this stays on the one code path already proven against the real
checkpoint, rather than a second, subtly different windowing implementation.
That recomputes older rows' features each time, which is cheap at this scale
(measured: 40,000 rows in 0.87s -- see ``scripts/fit_feature_scaler.py
--verify``) but would grow unbounded over a multi-hour session without a cap.
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.inference_client import LSTMInferenceClient  # noqa: E402
from src.siem.hybrid_scorer import HybridThreatScorer  # noqa: E402
from src.siem.playbook_engine import PlaybookEngine  # noqa: E402
from src.siem.rule_engine import ElasticSIEMCorrelator  # noqa: E402

from scripts.generate_transaction_batch import (  # noqa: E402
    CLEAN_MERCHANTS,
    CUSTOMERS,
    LOCATIONS,
    WATCHLIST_MERCHANTS,
    Txn,
    _build_es,
    _env_value,
    attach_history,
    score_with_model,
    transaction_doc,
)

SYDNEY_TZ = ZoneInfo("Australia/Sydney")

# Composition of what a tick generates. "slow_burn" always lands on
# CUST-18656 -- the documented scenario every other doc in this repo
# cross-references -- everything else draws a random customer.
# "off_hours" only fires when it is genuinely off-hours right now; see
# _pick_profile.
PROFILE_WEIGHTS: dict[str, float] = {
    "routine": 0.52,
    "high_value": 0.06,
    "geo": 0.07,
    "off_hours": 0.05,
    "watchlist": 0.06,
    # "attack" is the only profile that reliably crosses the 0.70 FLAGGED
    # line on its own -- the others each trigger a single rule, which caps
    # the blended score at 0.132 (0.33 siem_score x 0.40) without the model
    # independently agreeing. At the original 0.04 weight a live public demo
    # could sit for several minutes between flagged cases; raised so a viewer
    # watching the dashboard sees one within roughly a minute, while routine
    # traffic still dominates the feed.
    "attack": 0.18,
    "slow_burn": 0.06,
}


@dataclass
class CustomerState:
    """A simulated customer's running state across the session.

    Carrying this forward -- rather than drawing a fresh, unrelated balance
    and location every tick -- is what makes Rule 2 (impossible travel) and a
    draining balance emerge from the customer's own history instead of being
    hand-placed.
    """

    balance: float
    location: str
    when: datetime


def _is_off_hours(now: datetime) -> bool:
    local = now.astimezone(SYDNEY_TZ)
    return local.hour < 8 or local.hour >= 22


def _pick_profile(rng: random.Random, now: datetime) -> str:
    """Weighted profile draw. off_hours is only ever offered when it's true."""
    weights = dict(PROFILE_WEIGHTS)
    off_hours_weight = weights.pop("off_hours")
    if _is_off_hours(now):
        weights["off_hours"] = off_hours_weight * 4  # make it visible while it's genuinely true
    else:
        weights["routine"] += off_hours_weight  # redistribute rather than lie about the clock
    names, w = zip(*weights.items())
    return rng.choices(names, weights=w, k=1)[0]


def _build_tick(
    profile: str,
    rng: random.Random,
    now: datetime,
    states: dict[str, CustomerState],
) -> Txn:
    """Construct one transaction, carrying the customer's own history forward."""
    customer_id = "CUST-18656" if profile == "slow_burn" else rng.choice(CUSTOMERS)
    state = states.get(customer_id)
    if state is None:
        # First sighting this session: no prior location to compare against,
        # so prev == current (no travel claim) rather than a fabricated jump.
        start_location = "Darwin, NT" if profile == "slow_burn" else rng.choice(list(LOCATIONS))
        state = CustomerState(
            balance=round(rng.uniform(1_500, 45_000), 2),
            location=start_location,
            when=now - timedelta(minutes=rng.uniform(20, 180)),
        )
        states[customer_id] = state

    draining = profile == "attack"
    location = state.location
    channel = rng.choice(["Card", "Online"])
    txn_type = "PAYMENT"
    merchant = rng.choice(CLEAN_MERCHANTS)
    intent = "ordinary payment"

    if profile == "high_value":
        txn_type, channel, intent = "TRANSFER", "Online", "large amount"
    elif profile == "geo":
        other = [loc for loc in LOCATIONS if loc != state.location]
        location = rng.choice(other)
        intent = "location changed since last transaction"
    elif profile == "off_hours":
        intent = "off-hours transaction"
    elif profile == "watchlist":
        merchant, channel, intent = rng.choice(WATCHLIST_MERCHANTS), "Online", "watchlisted merchant"
    elif profile == "attack":
        other = [loc for loc in LOCATIONS if loc != state.location]
        location = rng.choice(other)
        merchant, channel, txn_type = rng.choice(WATCHLIST_MERCHANTS), "Online", "TRANSFER"
        intent = "coordinated attack"
        # A believable attack targets an account with something worth taking,
        # regardless of what this customer's balance happened to drift to.
        state.balance = max(state.balance, round(rng.uniform(11_000, 32_000), 2))
    elif profile == "slow_burn":
        location = "Darwin, NT"
        intent = "slow burn (rapid small payments, rules all pass)"

    old_balance_orig = state.balance
    if draining:
        amount = round(old_balance_orig * rng.uniform(0.85, 1.0), 2)
        new_balance_orig = round(max(0.0, old_balance_orig - amount), 2)
    else:
        amount_ranges = {
            "routine": (4.50, 480.00),
            "high_value": (10_500, 24_000),
            "geo": (180, 2_400),
            "off_hours": (60, 900),
            "watchlist": (120, 1_900),
            "slow_burn": (48, 320),
        }
        amount = round(rng.uniform(*amount_ranges[profile]), 2)
        if amount > old_balance_orig:
            # This customer's carried balance can't cover it -- top up, the
            # same way a real account might have just received a deposit.
            old_balance_orig = round(amount + rng.uniform(500, 5_000), 2)
        # A small, unmodelled inflow between transactions (salary, transfers
        # in) so a long session's balances don't monotonically drain to zero.
        new_balance_orig = round(
            old_balance_orig - amount + rng.uniform(0, amount * 0.4), 2
        )

    old_balance_dest = round(rng.uniform(0, 60_000), 2)
    if draining:
        # Mule account: money in, money straight back out.
        new_balance_dest = round(old_balance_dest + amount * rng.uniform(0.0, 0.12), 2)
    else:
        new_balance_dest = round(old_balance_dest + amount, 2)

    txn = Txn(
        customer_id=customer_id,
        amount=amount,
        merchant=merchant,
        location=location,
        prev_location=state.location,
        when=now,
        prev_when=state.when,
        channel=channel,
        txn_type=txn_type,
        profile=profile,
        intent=intent,
        old_balance_orig=old_balance_orig,
        new_balance_orig=new_balance_orig,
        old_balance_dest=old_balance_dest,
        new_balance_dest=new_balance_dest,
        is_fraud=1 if profile in ("attack", "slow_burn") else 0,
    )

    state.balance = new_balance_orig
    state.location = location
    state.when = now
    return txn


def run(
    interval_min: float,
    interval_max: float,
    duration: float | None,
    max_history: int,
    seed: int | None,
) -> int:
    """Stream transactions until Ctrl+C or --duration elapses."""
    correlator = ElasticSIEMCorrelator()

    client = LSTMInferenceClient(_env_value("LSTM_SERVING_URL", "http://localhost:8080"), timeout=30)
    if not client.health_check():
        print("\n[!] LSTM inference API is not reachable.")
        print("    Start the stack first:  docker compose up -d")
        return 1

    try:
        es = _build_es()
        if not es.ping():
            raise ConnectionError("ping failed")
    except Exception as exc:  # noqa: BLE001
        print(f"\n[!] Elasticsearch is not reachable: {exc}")
        print("    Start the stack first:  docker compose up -d")
        return 1

    playbook = PlaybookEngine(es_client=es)
    scorer = HybridThreatScorer(playbook_engine=playbook)
    rng = random.Random(seed)

    print("\nMERIDIAN SENTINEL - live transaction stream")
    print(f"One transaction every {interval_min:.0f}-{interval_max:.0f}s, real time, real model.")
    print("Dashboard : cd frontend && npm run dev  ->  http://localhost:5173")
    print("Kibana    : http://localhost:5601  ->  Fraud Detection Overview")
    print("Ctrl+C to stop.\n")

    header = f"{'#':>5}  {'time':<9} {'customer':<11} {'amount':>11}  {'rules':<8} {'beh':>5} {'risk':>5}  {'verdict':<8} why"
    print(header)
    print("-" * len(header))

    all_txns: list[Txn] = []
    states: dict[str, CustomerState] = {}
    n_ok = n_skipped = n_flagged = 0
    started = time.monotonic()

    try:
        while duration is None or (time.monotonic() - started) < duration:
            now = datetime.now(tz=timezone.utc)
            profile = _pick_profile(rng, now)
            txn = _build_tick(profile, rng, now, states)

            all_txns.append(txn)
            if len(all_txns) > max_history:
                all_txns.pop(0)

            scored, why = score_with_model(all_txns, client)
            if not scored:
                print(f"  [!] tick skipped -- model scoring failed: {why}")
                n_skipped += 1
                time.sleep(rng.uniform(interval_min, interval_max))
                continue

            # Rule 5 needs this customer's run of transactions, not just this
            # tick. Recomputed over the retained window each time so a customer
            # building up a burst is seen as one.
            attach_history(all_txns)

            txn.siem = correlator.evaluate(txn.event())
            txn.result = scorer.score(txn.lstm_score, txn.siem, txn.event())

            index = f"meridian-transactions-{now:%Y.%m.%d}"
            es.index(index=index, document=transaction_doc(txn))

            n_ok += 1
            is_flagged = txn.result["verdict"] == "FLAGGED"
            n_flagged += is_flagged
            fired = [r["rule_id"].replace("RULE_00", "R") for r in txn.siem["rules"] if r["triggered"]]

            local = now.astimezone(SYDNEY_TZ)
            print(
                f"{n_ok:>5}  {local:%H:%M:%S}  {txn.customer_id:<11} "
                f"${txn.amount:>10,.2f}  {','.join(fired) or 'ok':<8} "
                f"{txn.lstm_score:>5.2f} {txn.result['threat_score']:>5.2f}  "
                f"{'FLAGGED' if is_flagged else 'pass':<8} "
                f"{txn.result['trigger_reason'] if is_flagged else txn.intent}"
            )

            time.sleep(rng.uniform(interval_min, interval_max))
    except KeyboardInterrupt:
        print("\n\n  Stopped.")

    elapsed = time.monotonic() - started
    print(f"\n  {n_ok} transactions indexed, {n_flagged} flagged, {n_skipped} skipped over {elapsed:.0f}s.")
    print("  Every behaviour score above is real output from the served LSTM.\n")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Stream simulated transactions against the live stack.")
    parser.add_argument("--interval-min", type=float, default=2.0, help="minimum seconds between transactions")
    parser.add_argument("--interval-max", type=float, default=8.0, help="maximum seconds between transactions")
    parser.add_argument("--duration", type=float, default=None, help="stop automatically after N seconds (default: run forever)")
    parser.add_argument("--max-history", type=int, default=300, help="transactions kept in memory for feature computation")
    parser.add_argument("--seed", type=int, default=None, help="RNG seed (omit for a different stream each run)")
    args = parser.parse_args()
    sys.exit(run(args.interval_min, args.interval_max, args.duration, args.max_history, args.seed))


if __name__ == "__main__":
    main()
