"""Demo of Meridian Sentinel detection scenarios - built for presentations.

Runs a set of realistic fraud scenarios through the SIEM rule engine and hybrid
threat scorer and prints a plain-language summary of what the system decided and
why.

Two modes
---------
Offline (default)::

    python scripts/demo_scenarios.py

    Runs entirely in one Python process - no Docker needed. Security rules are
    computed for real; the AI score is a representative value per scenario.
    Safe to run anywhere as a fallback.

Live (against the running stack)::

    python scripts/demo_scenarios.py --live

    Calls the real LSTM inference API for each AI score, writes incidents to
    Elasticsearch, and indexes each transaction so it appears in the Kibana
    dashboard. Requires ``docker compose up -d`` and a healthy stack.

Environment (live mode)
-----------------------
    LSTM_SERVING_URL   default http://localhost:8080
    ELASTIC_HOST       default http://localhost:9200
    ELASTIC_PASSWORD   default meridian123
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np

# Silence the playbook/scorer INFO+WARNING logs so only the formatted demo
# output is shown during a presentation.
logging.disable(logging.CRITICAL)

# Make ``src`` importable when run from anywhere
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.inference_client import LSTMInferenceClient  # noqa: E402
from src.siem.hybrid_scorer import HybridThreatScorer  # noqa: E402
from src.siem.playbook_engine import PlaybookEngine  # noqa: E402
from src.siem.rule_engine import ElasticSIEMCorrelator  # noqa: E402

# Friendly names for each rule id (for non-technical output)
RULE_NAMES: dict[str, str] = {
    "RULE_001": "Large amount",
    "RULE_002": "Impossible travel (geo-velocity)",
    "RULE_003": "Odd hour",
    "RULE_004": "Known-bad merchant",
}

# Coordinates used to build believable location histories
SYDNEY = (-33.8688, 151.2093)
DARWIN = (-12.4634, 130.8456)
LONDON = (51.5074, -0.1278)

# Feature windows (5 transactions x 12 features) fed to the live LSTM model.
# A calm window (low, steady values) reads as normal; an escalating window
# (rising spend, rising frequency, geo-velocity flag set) reads as anomalous.
CALM_WINDOW = [
    [0.05, 0.10, 0.0, 0.0, 0.0, 5411, 1.0, 2.0, 0.10, 0.10, 0.20, 0.30],
    [0.06, 0.11, 0.0, 0.0, 0.0, 5411, 1.0, 2.0, 0.11, 0.10, 0.21, 0.31],
    [0.05, 0.12, 0.0, 0.0, 0.0, 5411, 1.0, 3.0, 0.12, 0.10, 0.22, 0.30],
    [0.07, 0.10, 0.0, 0.0, 0.0, 5411, 2.0, 3.0, 0.10, 0.11, 0.20, 0.32],
    [0.06, 0.11, 0.0, 0.0, 0.0, 5411, 1.0, 2.0, 0.11, 0.10, 0.21, 0.30],
]
ESCALATING_WINDOW = [
    [0.1, 0.2, 2.0, 1.0, 0.0, 5732, 3.0, 8.0, 0.5, 0.3, 0.8, 1.2],
    [0.2, 0.3, 2.0, 1.0, 0.0, 5732, 4.0, 9.0, 0.6, 0.3, 0.9, 1.3],
    [0.3, 0.4, 2.0, 0.0, 0.0, 5812, 5.0, 10.0, 0.7, 0.4, 1.0, 1.5],
    [0.4, 0.5, 2.0, 0.0, 1.0, 5732, 6.0, 11.0, 0.8, 0.5, 1.1, 1.8],
    [0.5, 0.6, 2.0, 1.0, 1.0, 5732, 7.0, 12.0, 0.9, 0.6, 1.2, 2.1],
]


def _event(
    customer_id: str,
    amount: float,
    location: tuple[float, float],
    prev_location: tuple[float, float],
    timestamp: str,
    prev_timestamp: str,
    merchant_id: str,
    channel: str,
) -> dict:
    """Assemble a transaction event dict in the shape the SIEM engine expects."""
    return {
        "customer_id": customer_id,
        "amount": amount,
        "lat": location[0],
        "lon": location[1],
        "prev_lat": prev_location[0],
        "prev_lon": prev_location[1],
        "timestamp": timestamp,
        "prev_timestamp": prev_timestamp,
        "merchant_id": merchant_id,
        "channel": channel,
    }


# Each scenario: title, plain-language story, event, feature window for the live
# model, a representative AI score for offline mode, the ground-truth fraud flag,
# and the teaching point to say out loud.
SCENARIOS: list[dict] = [
    {
        "title": "1. Everyday payment (safe)",
        "story": "A customer buys groceries in Sydney at 2pm from their usual "
                 "supermarket. Nothing about it is unusual.",
        "event": _event("CUST-10001", 86.40, SYDNEY, SYDNEY,
                        "2026-07-05T14:02:00+10:00", "2026-07-05T13:20:00+10:00",
                        "M0001", "CASH_OUT"),
        "features": CALM_WINDOW,
        "lstm_score": 0.10,
        "is_fraud": 0,
        "teaches": "This is what 'normal' looks like - no rules fire, the AI is "
                   "relaxed, and the payment is simply allowed.",
    },
    {
        "title": "2. Slow burn (the AI catches what the rules miss)",
        "story": "Six small card purchases in Darwin over 75 minutes - each one "
                 "is under every limit, in a normal city, at a normal time. No "
                 "single payment looks wrong.",
        "event": _event("CUST-18656", 256.74, DARWIN, DARWIN,
                        "2026-07-05T14:10:00+10:00", "2026-07-05T13:55:00+10:00",
                        "M5732", "PAYMENT"),
        "features": ESCALATING_WINDOW,
        "lstm_score": 0.74,
        "is_fraud": 1,
        "teaches": "Every security rule PASSES - a rules-only system would miss "
                   "this. But the AI has learned this customer's normal pattern "
                   "and the rapid-fire spending doesn't fit. The AI alone raises "
                   "it for review.",
    },
    {
        "title": "3. Odd hour only (a single rule is not enough)",
        "story": "A normal-sized $120 purchase in Sydney - but at 3am. The time "
                 "is unusual, yet the amount, location, and merchant are all fine.",
        "event": _event("CUST-52210", 120.00, SYDNEY, SYDNEY,
                        "2026-07-05T03:10:00+10:00", "2026-07-05T02:40:00+10:00",
                        "M0007", "PAYMENT"),
        "features": CALM_WINDOW,
        "lstm_score": 0.22,
        "is_fraud": 0,
        "teaches": "One medium rule fires, but the system keeps it under watch "
                   "rather than locking the account - a single weak signal is not "
                   "enough. This is how false alarms are kept low.",
    },
    {
        "title": "4. Known-bad merchant only (still just watched)",
        "story": "A $95 payment in daytime Sydney - but the merchant is already "
                 "on the fraud watchlist.",
        "event": _event("CUST-61845", 95.00, SYDNEY, SYDNEY,
                        "2026-07-05T15:20:00+10:00", "2026-07-05T14:50:00+10:00",
                        "M9921", "PAYMENT"),
        "features": CALM_WINDOW,
        "lstm_score": 0.30,
        "is_fraud": 0,
        "teaches": "The watchlist rule fires, but on its own it only raises the "
                   "risk part-way. The system waits for the AI to agree or for "
                   "more rules before acting.",
    },
    {
        "title": "5. Stolen card - impossible travel (geo-velocity)",
        "story": "A $12,500 transfer in London at 3:35am, just 30 minutes after "
                 "the same card was used in Sydney - a trip no human could make.",
        "event": _event("CUST-24417", 12_500.00, LONDON, SYDNEY,
                        "2026-07-05T03:35:00+10:00", "2026-07-05T03:05:00+10:00",
                        "M0002", "TRANSFER"),
        "features": ESCALATING_WINDOW,
        "lstm_score": 0.55,
        "is_fraud": 1,
        "teaches": "Three rules fire at once - the large amount, the impossible "
                   "travel speed, and the odd hour. Stacked together with a "
                   "raised AI score, the combined risk crosses the line and the "
                   "account is locked automatically.",
    },
    {
        "title": "6. Coordinated attack (highest urgency)",
        "story": "An $18,000 payment to a merchant already on the fraud watchlist, "
                 "in London at 3:35am, moments after the card was in Sydney.",
        "event": _event("CUST-31900", 18_000.00, LONDON, SYDNEY,
                        "2026-07-05T03:35:00+10:00", "2026-07-05T03:05:00+10:00",
                        "M9921", "TRANSFER"),
        "features": ESCALATING_WINDOW,
        "lstm_score": 0.92,
        "is_fraud": 1,
        "teaches": "Every warning sign at once - big amount, impossible travel, "
                   "odd hour, and a known-bad merchant, plus a very high AI score. "
                   "This is marked CRITICAL, the top urgency level.",
    },
]

_BAR_WIDTH = 24


def _bar(score: float) -> str:
    """Render a 0.0-1.0 score as a simple text bar for the terminal."""
    filled = int(round(score * _BAR_WIDTH))
    return "[" + "#" * filled + "-" * (_BAR_WIDTH - filled) + f"] {score:.2f}"


def _print_scenario(scenario: dict, siem: dict, result: dict, live: bool) -> None:
    """Print one scenario's outcome in plain, presentation-friendly language."""
    line = "=" * 66
    print(f"\n{line}\n {scenario['title']}\n{line}")
    print(f" Story: {scenario['story']}\n")

    print(" Security rules checked:")
    for rule in siem["rules"]:
        name = RULE_NAMES.get(rule["rule_id"], rule["rule_id"])
        if rule["triggered"]:
            detail = ""
            if rule["rule_id"] == "RULE_002":
                detail = f"  ({rule['evidence'].get('velocity_kmh')} km/h, limit 500)"
            elif rule["rule_id"] == "RULE_001":
                detail = f"  (${rule['evidence'].get('amount'):,.0f}, limit $10,000)"
            elif rule["rule_id"] == "RULE_003":
                detail = f"  (local time {rule['evidence'].get('local_time')})"
            print(f"   [ FIRED ] {name}{detail}")
        else:
            print(f"   [  ok   ] {name}")

    ai_tag = "live model" if live else "illustrative"
    print()
    print(f" AI behaviour score : {_bar(result['lstm_score'])}  ({ai_tag})")
    print(f" Security score     : {_bar(result['siem_score'])}")
    print(f" Overall risk       : {_bar(result['threat_score'])}")

    verdict = result["verdict"]
    if verdict == "FLAGGED":
        severity = result["incident"]["severity"] if result["incident"] else "HIGH"
        reason = {
            "LSTM_ALONE": "the AI flagged it on its own",
            "HYBRID_THRESHOLD": "the combined signals crossed the line",
        }.get(result["trigger_reason"], result["trigger_reason"])
        action = result["incident"]["action"] if result["incident"] else "LOCK_ACCOUNT"
        print(f"\n VERDICT            : FLAGGED FOR REVIEW  ({severity})")
        print(f" Why                : {reason}")
        print(f" Action taken       : {action.replace('_', ' ').title()}")
    else:
        print("\n VERDICT            : allowed (kept under watch)")

    print(f"\n Takeaway: {scenario['teaches']}")


def _env_file_value(key: str) -> str | None:
    """Read a single ``KEY=value`` from the project .env file, if present."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith(f"{key}="):
                return stripped.split("=", 1)[1].strip()
    return None


def _build_es_client():
    """Build an Elasticsearch client for live mode.

    The password is taken from the ELASTIC_PASSWORD environment variable, then
    the project .env file, then a default - so the demo always uses the same
    credentials the running stack was started with.
    """
    from elasticsearch import Elasticsearch

    host = os.environ.get("ELASTIC_HOST", "http://localhost:9200")
    password = (
        os.environ.get("ELASTIC_PASSWORD")
        or _env_file_value("ELASTIC_PASSWORD")
        or "meridian123"
    )
    return Elasticsearch(host, basic_auth=("elastic", password), request_timeout=10)


def _index_transaction(es, scenario: dict) -> None:
    """Index a transaction doc so it appears in the Kibana dashboard.

    The document is shaped to match the ECS fields the dashboard reads
    (transaction.type, transaction.amount, labels.is_fraud, source.geo.*).
    Uses ``@timestamp`` = now so it falls inside the default dashboard window.
    """
    event = scenario["event"]
    today = datetime.now(tz=timezone.utc).strftime("%Y.%m.%d")
    doc = {
        "@timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "transaction": {
            "type": event["channel"],
            "amount": event["amount"],
            "merchant_id": event["merchant_id"],
        },
        "labels": {"is_fraud": scenario["is_fraud"]},
        "source": {"geo": {"lat": event["lat"], "lon": event["lon"]}},
        "event": {"category": "financial", "type": "transaction"},
        "customer_id": event["customer_id"],
    }
    es.index(index=f"meridian-transactions-{today}", document=doc, refresh=True)


def run(live: bool) -> None:
    """Run every scenario through the SIEM engine and hybrid scorer."""
    correlator = ElasticSIEMCorrelator()

    lstm_client = None
    es = None
    if live:
        lstm_client = LSTMInferenceClient(
            os.environ.get("LSTM_SERVING_URL", "http://localhost:8080")
        )
        if not lstm_client.health_check():
            print("\n[!] LSTM inference API is not reachable.")
            print("    Start the stack first:  docker compose up -d")
            print("    Then wait until it is healthy:  docker compose ps")
            sys.exit(1)
        try:
            es = _build_es_client()
            if not es.ping():
                raise ConnectionError("ping failed")
        except Exception as exc:  # noqa: BLE001
            print(f"\n[!] Elasticsearch is not reachable: {exc}")
            print("    Start the stack first:  docker compose up -d")
            sys.exit(1)
        playbook = PlaybookEngine(es_client=es)
    else:
        playbook = PlaybookEngine(es_client=MagicMock())

    scorer = HybridThreatScorer(playbook_engine=playbook)

    mode = "LIVE (real model + Elasticsearch)" if live else "OFFLINE (illustrative)"
    print(f"\nMERIDIAN SENTINEL - Detection Demo  [{mode}]")
    print("Security rules are computed for real from the transaction data.")

    for scenario in SCENARIOS:
        siem = correlator.evaluate(scenario["event"])
        if live:
            score = lstm_client.predict(np.array(scenario["features"], dtype=np.float32))
        else:
            score = scenario["lstm_score"]
        result = scorer.score(score, siem, scenario["event"])
        if live:
            _index_transaction(es, scenario)
        _print_scenario(scenario, siem, result, live)

    print("\n" + "=" * 66)
    print(" How to read this")
    print("=" * 66)
    print(" - Security rules on their own can only push the risk part-way - the")
    print("   system waits for the AI to agree, or for several rules to stack,")
    print("   before it locks an account. That keeps false alarms down.")
    print(" - The 'slow burn' case is the headline: the AI catches fraud that")
    print("   breaks no rule at all.")
    if live:
        print("\n Open the Kibana dashboard to see these transactions and incidents:")
        print("   http://localhost:5601  ->  Dashboard  ->  Fraud Detection Overview")
        print("   (widen the date picker to 'Last 30 days' if panels look empty)")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Meridian Sentinel detection demo")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run against the live stack: real LSTM API + write to Elasticsearch",
    )
    args = parser.parse_args()
    run(live=args.live)


if __name__ == "__main__":
    main()
