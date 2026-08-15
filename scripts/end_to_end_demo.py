"""The complete monitoring flow, shown stage by stage, for real.

Runs transactions through ``TransactionPipeline`` and prints every stage it
passes: the transaction as received, all five rules with their evidence, the
LSTM inference call with its request id and tensor sizes, the blended decision,
the Elasticsearch document, and the audit trail joining them together.

Nothing here is scripted. Every number printed is produced by the same engines
the batch and live-stream scripts use; change an amount or a merchant id and
the output changes with it.

Three scenarios
---------------
``legit``      CUST-52210 — an ordinary $50.00 payment. Rules ALLOW, model
               scores it normal, verdict MONITOR.
``slow-burn``  CUST-18656 — six small Darwin payments over 75 minutes. Every
               *stateless* rule passes on every payment; Rule 5, which reads the
               customer's run rather than the single transaction, fires on the
               sixth.
``fraud``      CUST-24417 — a full-balance TRANSFER to a watchlisted mule in
               another city, off-hours. Multiple rules fire, the model scores it
               an anomaly, verdict FLAGGED and the playbook runs for real.

What this demo will NOT show, and why
-------------------------------------
The LSTM does not detect the slow burn, and the ``slow-burn`` scenario prints
its actual scores rather than an implied one. PaySim — the only dataset this
project trains on — averages 1.001 transactions per customer, and every
labelled fraud in it is a single isolated transaction, so 99.96% of training
windows were one real row padded with four rows of zeros. A slow burn is by
definition a multi-transaction shape; there was never an example of one in
training, fraudulent or otherwise. The sequence-level detector in this system
is SIEM Rule 5, deterministically. See MODEL_CARD.md Known Limitations item 7.

The contrast the slow-burn scenario demonstrates is therefore real but
differently attributed than a naive reading suggests: *stateless per-transaction
rules pass; stateful sequence analysis catches it*. That is the distinction
worth showing, and it is the one the output supports.

Why only the headline transaction is audited in scenarios A and C
-------------------------------------------------------------------
``cumulative_spend_ratio`` and ``amount_zscore`` (features 9 and 11) are
computed as ``groupby('nameOrig')['amount'].mean()/.std()`` over every row
sharing that customer in the batch handed to ``compute_feature_matrix`` — not
a causal, rows-seen-so-far mean. In PaySim (1.001 transactions/customer) that
distinction never mattered; here, where a scenario's earlier context
transactions and its headline transaction share one customer and one batch
call, the earlier rows' own scores shift depending on what shares their batch,
purely as an artifact of batch composition rather than their own content
(confirmed by comparing the same $84.20 Coles payment scoring 0.0023 in one
batch and 1.0000 in a differently-sized one). ``fifty_dollar_pass_check.py``
and ``fraud_transaction_fail_check.py`` already sidestep this by only ever
scoring ``target = txns[-1]`` — the context rows exist to populate its window,
never their own. This script follows the same precedent: scenarios A and C
audit only the final transaction; scenario B, whose whole point is scoring
every step of a real sequence, was already validated clean of this artifact
(its first transaction scores 0.0023, not an inflated value) and keeps its
existing per-transaction scoring.

On "tokens"
-----------
This is a tensor model, not a language model — it has no tokens. The equivalent
measure of data crossing the inference boundary is the element count of the
tensors: ``1 x 5 timesteps x 13 features = 65`` float32 values in, one
probability out. Those are the counts printed, under their real names.

Usage::

    # dry run - evaluates and prints everything, writes nothing
    docker compose --profile dev run --rm dev python -m scripts.end_to_end_demo

    # live - indexes to Elasticsearch, fires real playbooks, dashboard picks it up
    docker compose --profile dev run --rm \
        -e ELASTIC_HOST=http://elasticsearch:9200 \
        dev python -m scripts.end_to_end_demo --write

    # one scenario only
    ... python -m scripts.end_to_end_demo --scenario slow-burn --write
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.disable(logging.CRITICAL)

from src.inference_client import LSTMInferenceClient  # noqa: E402
from src.pipeline.orchestrator import TransactionPipeline, build_windows  # noqa: E402
from src.siem.hybrid_scorer import HybridThreatScorer  # noqa: E402
from src.siem.playbook_engine import PlaybookEngine  # noqa: E402
from src.siem.rule_engine import ElasticSIEMCorrelator  # noqa: E402

from scripts.generate_transaction_batch import (  # noqa: E402
    _build_es,
    _env_value,
    attach_history,
)

SYDNEY_TZ = ZoneInfo("Australia/Sydney")
WIDTH = 96

# Friendly rule names. The engine only carries rule_id; this mirrors the
# dashboard's own RULE_NAMES map so the console and the UI agree.
RULE_NAMES: dict[str, str] = {
    "RULE_001": "High-Value Transaction  (> $10,000)",
    "RULE_002": "Impossible Geo-Velocity (> 500 km/h)",
    "RULE_003": "Off-Hours Transaction   (outside 08:00-22:00 AEST)",
    "RULE_004": "Watchlist Merchant",
    "RULE_005": "Burst Velocity          (>=5 txns / 120 min taking >=20% balance)",
}

# 13 trained features, in the order the model expects them. Source of truth is
# FEATURE_COLS in src/pipeline/feature_engineering.py.
FEATURE_NAMES: list[str] = [
    "amount_delta", "balance_utilisation_ratio", "channel_type_encoded",
    "time_of_day_flag", "balance_drop_to_zero", "amount_to_balance_ratio",
    "transaction_frequency_1h", "transaction_frequency_24h",
    "cumulative_spend_ratio", "dest_received_ratio", "amount_zscore",
    "step_norm", "geo_velocity_kmh",
]


# Docker Compose service name -> the port it publishes on the host. Inside the
# dev container the pipeline talks to `http://lstm-serving:8080`, which is the
# real endpoint and is what the audit trail records. That hostname only resolves
# on the Compose network, though, so pasting it into a browser on the host gives
# DNS_PROBE_FINISHED_NXDOMAIN. This maps each internal name to the address that
# reaches the same service from the host.
_SERVICE_TO_HOST_PORT: dict[str, int] = {
    "lstm-serving": 8080,
    "elasticsearch": 9200,
    "kibana": 5601,
}


def browser_url(url: str) -> str:
    """Rewrite a Compose-internal URL to one the host's browser can open.

    Returns the URL unchanged when it does not name a known service, so a run
    started outside Docker (already pointing at localhost) is unaffected.
    """
    for service, port in _SERVICE_TO_HOST_PORT.items():
        if f"//{service}:" in url:
            return url.replace(f"//{service}:", "//localhost:")
        if f"//{service}/" in url or url.endswith(f"//{service}"):
            return url.replace(f"//{service}", f"//localhost:{port}")
    return url


def rule(title: str = "", char: str = "=") -> None:
    """Print a titled separator."""
    if title:
        print("\n" + char * WIDTH)
        print(title)
        print(char * WIDTH)
    else:
        print(char * WIDTH)


def show_transaction(txn, n: int, total: int) -> None:
    """Stage 1 — the transaction as the pipeline received it."""
    local = txn.when.astimezone(SYDNEY_TZ)
    print(f"\n--- transaction {n} of {total} " + "-" * (WIDTH - 24))
    print(f"  customer      : {txn.customer_id}")
    print(f"  amount        : A${txn.amount:,.2f}")
    print(f"  merchant      : {txn.merchant[0]}  {txn.merchant[1]}  "
          f"(MCC {txn.merchant[2]} {txn.merchant[3]})")
    print(f"  timestamp     : {local:%Y-%m-%d %H:%M:%S %Z}")
    print(f"  location      : {txn.location}   (previous: {txn.prev_location})")
    print(f"  channel/type  : {txn.channel} / {txn.txn_type}")
    print(f"  balance       : A${txn.old_balance_orig:,.2f} -> "
          f"A${txn.new_balance_orig:,.2f}")
    print(f"  history known : {len(txn.recent)} prior transaction(s) for this customer")


def show_rules(siem: dict) -> None:
    """Stage 2 — every rule, its verdict, and the evidence behind it."""
    print("\n  RULE ENGINE")
    print(f"  {'rule':<10} {'result':<8} {'sev':<7} name")
    print("  " + "-" * (WIDTH - 4))
    for r in siem["rules"]:
        verdict = "FAIL" if r["triggered"] else "pass"
        print(f"  {r['rule_id']:<10} {verdict:<8} {r['severity']:<7} "
              f"{RULE_NAMES.get(r['rule_id'], r['rule_id'])}")

    triggered = [r for r in siem["rules"] if r["triggered"]]
    for r in triggered:
        print(f"\n    evidence for {r['rule_id']}:")
        for k, v in r["evidence"].items():
            print(f"      {k:<22} {v}")

    decision = "FLAG" if triggered else "ALLOW"
    print(f"\n  rule engine decision : {decision}"
          f"   ({len(triggered)} of {len(siem['rules'])} rules triggered)")
    print(f"  siem_score           : {siem['siem_score']:.2f}"
          "   (0 rules=0.00, 1=0.33, 2=0.67, 3+=1.00)")


def show_inference(outcome, window) -> None:
    """Stages 3 and 4 — the inference call, in full."""
    meta = outcome.inference.metadata
    print("\n  LSTM INFERENCE")
    print("  input tensor [1, 5, 13] - 5 timesteps x 13 MinMax-scaled features")
    print(f"  {'t':<4} " + " ".join(f"{n[:7]:>7}" for n in FEATURE_NAMES))
    for i, step in enumerate(window):
        pad = " (zero-pad)" if float(step.sum()) == 0.0 else ""
        print(f"  t-{4 - i:<2} " + " ".join(f"{v:>7.3f}" for v in step) + pad)

    endpoint = outcome.trail.records[2].detail.get("endpoint", "")
    print(f"\n    endpoint (called)   : {endpoint}")
    if browser_url(endpoint) != endpoint:
        print(f"    endpoint (browser)  : {browser_url(endpoint)}"
              "   <- open this one on the host")
    print(f"    request_id          : {outcome.inference.request_id}")
    print(f"    model               : {meta.get('model_name')} v{outcome.inference.model_version}")
    print(f"    inference_timestamp : {meta.get('inference_timestamp')}")
    print(f"    input  shape/count  : {meta.get('input_shape')} = "
          f"{outcome.inference.input_elements} float32 values")
    print(f"    output shape/count  : {meta.get('output_shape')} = "
          f"{outcome.inference.output_elements} scalar")
    print(f"    server latency      : {meta.get('latency_ms')} ms  "
          f"(ONNX session only)")
    print(f"    round trip          : {outcome.inference.round_trip_ms} ms  "
          f"(incl. HTTP + JSON)")
    print(f"    anomaly probability : {outcome.result['lstm_score']:.4f}")
    print(f"    decision threshold  : {meta.get('decision_threshold')}")
    verdict = ("ANOMALY" if outcome.result["lstm_score"]
               >= float(meta.get("decision_threshold", 0.90)) else "NORMAL")
    print(f"    model assessment    : {verdict}")


def show_decision(outcome) -> None:
    """Stage 5 — the blend and the verdict."""
    r = outcome.result
    print("\n  HYBRID DECISION")
    print("    threat_score = lstm x 0.60 + siem x 0.40")
    print(f"                 = {r['lstm_score']:.4f} x 0.60 + {r['siem_score']:.2f} x 0.40")
    print(f"                 = {r['threat_score']:.4f}      (flag line 0.70)")
    print(f"    verdict        : {r['verdict']}")
    print(f"    trigger_reason : {r['trigger_reason']}")
    print(f"    playbook fired : {r['playbook_fired']}")
    if r.get("incident"):
        inc = r["incident"]
        print(f"    incident_id    : {inc['incident_id']}")
        print(f"    severity       : {inc['severity']}")
        print(f"    action         : {inc['action']}")


def show_document(outcome, full: bool) -> None:
    """Stage 6 — the Elasticsearch document."""
    print("\n  ELASTICSEARCH DOCUMENT")
    if outcome.indexed_id:
        print(f"    _id             : {outcome.indexed_id}")
    doc = outcome.document
    if full:
        print(json.dumps(doc, indent=6, default=str))
    else:
        keys = ["correlation_id", "customer_id", "amount", "merchant_name",
                "siem_pass", "triggered_rules", "lstm_score", "siem_score",
                "threat_score", "verdict", "trigger_reason", "lstm_score_source"]
        for k in keys:
            print(f"    {k:<20} {doc.get(k)}")
        print(f"    inference           {json.dumps(doc.get('inference', {}), default=str)}")


def run_scenario(name: str, title: str, txns: list[Any], pipeline: TransactionPipeline,
                 full_doc: bool, note: str = "", audit_all: bool = True) -> list[Any]:
    """Run one scenario end to end, printing every stage.

    Args:
        audit_all: When True (the slow-burn scenario), every transaction runs
            through the full audited pipeline — the sequence building up is
            the point. When False (legit/fraud), only the final transaction is
            audited; earlier ones are indexed as plain history, matching
            fifty_dollar_pass_check.py/fraud_transaction_fail_check.py's own
            precedent — see the module docstring for why.
    """
    rule(f"SCENARIO: {title}")
    if note:
        print(note)

    attach_history(txns)
    windows = build_windows(txns)

    audit_positions = (
        set(range(len(txns))) if audit_all else {len(txns) - 1}
    )

    outcomes = []
    for i, (txn, window) in enumerate(zip(txns, windows)):
        show_transaction(txn, i + 1, len(txns))

        if i not in audit_positions:
            print("\n  (context transaction — indexed for history, not "
                  "individually audited; see module docstring)")
            pipeline.index_context_only(txn)
            continue

        outcome = pipeline.process(txn, window)
        outcomes.append(outcome)

        show_rules(outcome.siem)
        show_inference(outcome, window)
        show_decision(outcome)
        show_document(outcome, full_doc and i == len(txns) - 1)

        print("\n  AUDIT TRAIL")
        print(outcome.trail.render(indent="    "))

    return outcomes


def scenario_legit() -> tuple[str, list[Any], str]:
    from scripts.fifty_dollar_pass_check import build_session
    return (
        "A - LEGITIMATE  ($50.00, CUST-52210)",
        build_session(),
        "  An ordinary card payment in business hours at a clean merchant, with\n"
        "  the balance left largely intact. Expect: rules ALLOW, model NORMAL,\n"
        "  verdict MONITOR, no playbook.",
    )


def scenario_slow_burn() -> tuple[str, list[Any], str]:
    from scripts.slow_burn_check import build_session
    return (
        "B - SLOW BURN  (6 payments / 75 min, CUST-18656)",
        build_session(),
        "  Every payment below is small, in business hours, in one city, at a\n"
        "  merchant nobody has watchlisted. Rules 1-4 judge each transaction in\n"
        "  isolation and pass all of them. Rule 5 reads the customer's run and\n"
        "  fires once the window holds 5+ payments taking 20%+ of the balance.\n"
        "\n"
        "  Watch the LSTM column: it stays low throughout. The model was trained\n"
        "  on PaySim, which averages 1.001 transactions per customer, so it never\n"
        "  saw a multi-transaction sequence and has nothing to say about one.\n"
        "  The sequence detector here is Rule 5, not the model.",
    )


def scenario_fraud() -> tuple[str, list[Any], str]:
    from scripts.fraud_transaction_fail_check import build_session
    return (
        "C - FLAGGED FRAUD  (full-balance TRANSFER, CUST-24417)",
        build_session(),
        "  A balance-draining TRANSFER to a watchlisted mule account in another\n"
        "  city, off-hours. Expect: several rules FAIL, model ANOMALY, verdict\n"
        "  FLAGGED, and the playbook writes a real incident.",
    )


SCENARIOS = {
    "legit": scenario_legit,
    "slow-burn": scenario_slow_burn,
    "fraud": scenario_fraud,
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the complete monitoring flow, stage by stage."
    )
    parser.add_argument("--write", action="store_true",
                        help="index to Elasticsearch and fire real playbooks")
    parser.add_argument("--scenario", choices=[*SCENARIOS, "all"], default="all",
                        help="which scenario to run (default: all)")
    parser.add_argument("--full-doc", action="store_true",
                        help="print the complete ES document for the last "
                             "transaction of each scenario")
    args = parser.parse_args()

    base_url = _env_value("LSTM_SERVING_URL", "http://localhost:8080")
    client = LSTMInferenceClient(base_url, timeout=30)
    if not client.health_check():
        print(f"[!] LSTM inference API not reachable at {base_url}")
        print("    Start the stack first: docker compose up -d")
        return 1

    es = None
    playbook = None
    if args.write:
        es = _build_es()
        if not es.ping():
            print("[!] Elasticsearch not reachable - cannot --write.")
            print("    Start the stack first: docker compose up -d")
            return 1
        playbook = PlaybookEngine(es_client=es)

    pipeline = TransactionPipeline(
        client=client,
        correlator=ElasticSIEMCorrelator(),
        scorer=HybridThreatScorer(playbook_engine=playbook),
        es_client=es,
    )

    mode = "WRITE (indexing + real playbooks)" if args.write else "DRY RUN (nothing written)"
    rule("MERIDIAN SENTINEL - complete transaction monitoring flow")
    print(f"  mode        : {mode}")
    print(f"  inference   : {base_url}")
    if browser_url(base_url) != base_url:
        print(f"                ({browser_url(base_url)} from a browser on the host)")
    print(f"  run at      : {datetime.now(tz=SYDNEY_TZ):%Y-%m-%d %H:%M:%S %Z}")
    print("\n  Stage order: received -> rules -> inference -> decision -> "
          "playbook\n               -> elasticsearch -> dashboard, audited at each step.")

    names = [args.scenario] if args.scenario != "all" else list(SCENARIOS)
    all_outcomes: dict[str, list] = {}
    for name in names:
        title, txns, note = SCENARIOS[name]()
        all_outcomes[name] = run_scenario(
            name, title, txns, pipeline, args.full_doc, note,
            audit_all=(name == "slow-burn"),
        )

    # -- summary -------------------------------------------------------------
    rule("SUMMARY")
    header = (f"  {'scenario':<12} {'txns':>4}  {'rules fired':<14} "
              f"{'lstm max':>8} {'threat max':>10}  {'final verdict':<9}")
    print(header)
    print("  " + "-" * (len(header) - 2))
    for name, outcomes in all_outcomes.items():
        fired = sorted({r for o in outcomes for r in o.triggered_rules})
        lstm_max = max(o.result["lstm_score"] for o in outcomes)
        threat_max = max(o.result["threat_score"] for o in outcomes)
        verdict = "FLAGGED" if any(o.flagged for o in outcomes) else "MONITOR"
        short = ",".join(r.replace("RULE_00", "R") for r in fired) or "none"
        print(f"  {name:<12} {len(outcomes):>4}  {short:<14} "
              f"{lstm_max:>8.4f} {threat_max:>10.4f}  {verdict:<9}")

    # -- browser URLs --------------------------------------------------------
    # Everything above prints Compose-internal hostnames, because those are the
    # endpoints actually called and recorded. None of them resolve from the
    # host's browser, so the addresses that do are collected here in one block.
    rule("OPEN THESE IN YOUR BROWSER  (host addresses, not the internal ones above)")
    print(f"  React dashboard   : {'http://localhost:5173':<42} live transaction feed")
    print(f"  Inference API     : {'http://localhost:8080/docs':<42} Swagger UI - call the model")
    print(f"  Model status      : {'http://localhost:8080/v1/models/lstm':<42} version + threshold")
    print(f"  Kibana Discover   : {'http://localhost:5601/app/discover':<42} set range to Last 24 hours")
    print(f"  Elasticsearch     : {'http://localhost:9200':<42} needs elastic / $ELASTIC_PASSWORD")
    print("\n  The pipeline calls the internal names (lstm-serving:8080,")
    print("  elasticsearch:9200) because it runs inside the Compose network.")
    print("  Those only resolve between containers - use the addresses above")
    print("  from the host, or the browser reports DNS_PROBE_FINISHED_NXDOMAIN.")

    if args.write:
        index = f"meridian-transactions-{datetime.now(tz=timezone.utc):%Y.%m.%d}"
        audit_index = f"meridian-audit-{datetime.now(tz=timezone.utc):%Y.%m.%d}"
        print(f"\n  Indexed to    : {index}")
        print(f"  Audit trail   : {audit_index}  (+ logs/audit/*.jsonl)")
        first = next(iter(all_outcomes.values()))[-1]
        print("\n  Trace one transaction end to end by its correlation id:")
        print(f"    curl -u elastic:$ELASTIC_PASSWORD "
              f"'http://localhost:9200/meridian-audit-*/_search"
              f"?q=correlation_id:\"{first.correlation_id}\"&sort=sequence:asc&pretty'")
        print("\n  Or in Kibana Discover, data view meridian-audit-*, query:")
        print(f"    correlation_id : \"{first.correlation_id}\"")
    else:
        print("\n  Nothing was written. Re-run with --write to index it.")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
