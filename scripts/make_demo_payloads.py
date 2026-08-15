"""Emit ready-to-paste inference payloads for a live demonstration.

Builds the real feature tensors for a legitimate transaction and a fraudulent
one using the project's own feature pipeline, writes each as a JSON file, and
calls the served model with both so the expected answer is known before anyone
is watching.

The point is to be able to hand an examiner a payload, paste it into the
Swagger UI at ``/docs``, and have the model score it live — with the scores
already verified, so there are no surprises.

Usage::

    docker compose --profile dev run --rm dev python -m scripts.make_demo_payloads

Writes ``demo_payloads/legit.json`` and ``demo_payloads/fraud.json``.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.disable(logging.CRITICAL)

from src.inference_client import LSTMInferenceClient  # noqa: E402
from src.pipeline.orchestrator import build_windows  # noqa: E402

from scripts.generate_transaction_batch import _env_value, attach_history  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent.parent / "demo_payloads"

FEATURE_NAMES = [
    "amount_delta", "balance_utilisation_ratio", "channel_type_encoded",
    "time_of_day_flag", "balance_drop_to_zero", "amount_to_balance_ratio",
    "transaction_frequency_1h", "transaction_frequency_24h",
    "cumulative_spend_ratio", "dest_received_ratio", "amount_zscore",
    "step_norm", "geo_velocity_kmh",
]


def build(name: str, loader) -> dict:
    """Build one scenario's payload and score it through the served model."""
    txns = loader()
    attach_history(txns)
    windows = build_windows(txns)

    target = txns[-1]
    window = windows[-1]
    payload = {"instances": [window.tolist()]}

    OUT_DIR.mkdir(exist_ok=True)
    path = OUT_DIR / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    base_url = _env_value("LSTM_SERVING_URL", "http://localhost:8080")
    client = LSTMInferenceClient(base_url, timeout=30)
    result = client.predict_batch_with_metadata(window[None, ...])

    return {
        "name": name,
        "path": path,
        "customer": target.customer_id,
        "amount": target.amount,
        "merchant": target.merchant[1],
        "score": result.scores[0],
        "request_id": result.request_id,
        "latency": result.metadata.get("latency_ms"),
        "threshold": result.metadata.get("decision_threshold", 0.90),
        "window": window,
    }


def main() -> int:
    from scripts.fifty_dollar_pass_check import build_session as legit
    from scripts.fraud_transaction_fail_check import build_session as fraud

    print("\nBuilding demonstration payloads from the real feature pipeline\n")
    results = [build("legit", legit), build("fraud", fraud)]

    for r in results:
        threshold = float(r["threshold"])
        verdict = "ANOMALY" if r["score"] >= threshold else "NORMAL"
        print("=" * 78)
        print(f"{r['name'].upper()}  ->  {r['path'].parent.name}/{r['path'].name}")
        print("=" * 78)
        print(f"  customer            : {r['customer']}")
        print(f"  amount              : A${r['amount']:,.2f}")
        print(f"  merchant            : {r['merchant']}")
        print(f"  anomaly probability : {r['score']:.4f}")
        print(f"  threshold           : {threshold}")
        print(f"  model assessment    : {verdict}")
        print(f"  request_id          : {r['request_id']}")
        print(f"  server latency      : {r['latency']} ms")
        print("\n  final timestep (this transaction's own features):")
        for fname, val in zip(FEATURE_NAMES, r["window"][-1]):
            print(f"    {fname:<28} {val:>10.4f}")
        print()

    print("=" * 78)
    print("HOW TO RUN THESE LIVE")
    print("=" * 78)
    print("  Swagger UI : http://lstm-serving:8080/docs")
    print("               -> POST /v1/models/lstm:predict -> Try it out")
    print("               -> paste the contents of demo_payloads/<name>.json")
    print("               -> Execute")
    print()
    print("  curl       : curl -X POST http://localhost:8080/v1/models/lstm:predict \\")
    print("                    -H 'Content-Type: application/json' \\")
    print("                    -d @demo_payloads/fraud.json")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
