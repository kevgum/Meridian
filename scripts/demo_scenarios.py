"""Live demo of Meridian Sentinel detection scenarios - built for presentations.

Runs a set of realistic fraud scenarios through the *real* SIEM rule engine and
hybrid threat scorer and prints a plain-language summary of what the system
decided and why. No Docker, Elasticsearch, or GPU required - everything runs in
one Python process, so it is safe to run live in front of an audience.

Run from the repository root::

    python scripts/demo_scenarios.py

Each scenario shows:
  * a plain-English story of what happened,
  * which security rules fired (computed for real from the event data),
  * the AI behaviour score (illustrative - see note below),
  * the combined risk score, the verdict, and the automatic action.

Note on the AI score
--------------------
The security-rule results (large amount, impossible travel, odd hour, known-bad
merchant) are computed for real by ``ElasticSIEMCorrelator``. The AI behaviour
score is supplied per scenario as a representative value, because a real score
needs the trained LSTM model and a 5-transaction feature window. With the live
inference API running you would feed the model output in here instead.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Silence the playbook/scorer INFO+WARNING logs so only the formatted demo
# output is shown during a presentation.
logging.disable(logging.CRITICAL)

# Make ``src`` importable when run from anywhere
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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


def _event(
    customer_id: str,
    amount: float,
    location: tuple[float, float],
    prev_location: tuple[float, float],
    timestamp: str,
    prev_timestamp: str,
    merchant_id: str,
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
    }


# Each scenario: title, plain-language story, event, illustrative AI score,
# and the teaching point to say out loud.
SCENARIOS: list[dict] = [
    {
        "title": "1. Everyday payment (safe)",
        "story": "A customer buys groceries in Sydney at 2pm from their usual "
                 "supermarket. Nothing about it is unusual.",
        "event": _event(
            "CUST-10001", 86.40, SYDNEY, SYDNEY,
            "2026-07-05T14:02:00+10:00", "2026-07-05T13:20:00+10:00", "M0001",
        ),
        "lstm_score": 0.10,
        "teaches": "This is what 'normal' looks like - no rules fire, the AI is "
                   "relaxed, and the payment is simply allowed.",
    },
    {
        "title": "2. Slow burn (the AI catches what the rules miss)",
        "story": "Six small card purchases in Darwin over 75 minutes - each one "
                 "is under every limit, in a normal city, at a normal time. No "
                 "single payment looks wrong.",
        "event": _event(
            "CUST-18656", 256.74, DARWIN, DARWIN,
            "2026-07-05T14:10:00+10:00", "2026-07-05T13:55:00+10:00", "M5732",
        ),
        "lstm_score": 0.74,
        "teaches": "Every security rule PASSES - a rules-only system would miss "
                   "this. But the AI has learned this customer's normal pattern "
                   "and the rapid-fire spending doesn't fit. The AI alone raises "
                   "it for review.",
    },
    {
        "title": "3. Stolen card - impossible travel (geo-velocity)",
        "story": "A $12,500 transfer in London at 3:35am, just 30 minutes after "
                 "the same card was used in Sydney - a trip no human could make.",
        "event": _event(
            "CUST-24417", 12_500.00, LONDON, SYDNEY,
            "2026-07-05T03:35:00+10:00", "2026-07-05T03:05:00+10:00", "M0002",
        ),
        "lstm_score": 0.55,
        "teaches": "Three rules fire at once - the large amount, the impossible "
                   "travel speed, and the odd hour. Stacked together with a "
                   "raised AI score, the combined risk crosses the line and the "
                   "account is locked automatically.",
    },
    {
        "title": "4. Coordinated attack (highest urgency)",
        "story": "An $18,000 payment to a merchant already on the fraud watchlist, "
                 "in London at 3:35am, moments after the card was in Sydney.",
        "event": _event(
            "CUST-31900", 18_000.00, LONDON, SYDNEY,
            "2026-07-05T03:35:00+10:00", "2026-07-05T03:05:00+10:00", "M9921",
        ),
        "lstm_score": 0.92,
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


def _print_scenario(scenario: dict, siem: dict, result: dict) -> None:
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

    print()
    print(f" AI behaviour score : {_bar(result['lstm_score'])}")
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


def run() -> None:
    """Run every scenario through the real SIEM engine and hybrid scorer."""
    correlator = ElasticSIEMCorrelator()
    # MagicMock ES client so the playbook runs without a live Elasticsearch
    scorer = HybridThreatScorer(playbook_engine=PlaybookEngine(es_client=MagicMock()))

    print("\nMERIDIAN SENTINEL - Detection Demo")
    print("Security rules are computed for real; the AI score is illustrative.")

    for scenario in SCENARIOS:
        siem = correlator.evaluate(scenario["event"])
        result = scorer.score(scenario["lstm_score"], siem, scenario["event"])
        _print_scenario(scenario, siem, result)

    print("\n" + "=" * 66)
    print(" How to read this")
    print("=" * 66)
    print(" - Security rules on their own can only push the risk part-way - the")
    print("   system waits for the AI to agree, or for several rules to stack,")
    print("   before it locks an account. That keeps false alarms down.")
    print(" - The 'slow burn' case is the headline: the AI catches fraud that")
    print("   breaks no rule at all.\n")


if __name__ == "__main__":
    run()
