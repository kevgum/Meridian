"""
Smoke tests for the LSTM Inference API (Day 6).

Requires the lstm-serving container to be running:
    docker-compose up -d lstm-serving

Run:
    pytest tests/test_inference_api.py -v
"""

import os
import time
import numpy as np
import pytest
import requests

from src.inference_client import LSTMInferenceClient

# Read from env so the Docker dev container uses http://lstm-serving:8080
# while local runs outside Docker fall back to http://localhost:8080
BASE_URL = os.environ.get("LSTM_SERVING_URL", "http://localhost:8080")
THRESHOLD = 0.90


@pytest.fixture(scope="module")
def client():
    c = LSTMInferenceClient(BASE_URL)
    if not c.health_check():
        pytest.skip("lstm-serving container not running — start with: docker-compose up -d lstm-serving")
    return c


def test_health_check(client):
    """API returns AVAILABLE status."""
    r = requests.get(f"{BASE_URL}/v1/models/lstm")
    assert r.status_code == 200
    body = r.json()
    assert body["model_version_status"][0]["state"] == "AVAILABLE"


def test_clean_transaction_low_score(client):
    """A genuinely ordinary transaction's real, feature-engineered window
    should return a low anomaly probability.

    NOT an all-zeros vector: MinMax-scaled 0 means "the training set's
    minimum observed value" for each feature individually, not "typical" —
    for a wide-range feature like amount_delta (fitted range roughly
    [-19.3M, 3.2M]) that minimum is itself an extreme outlier, not a neutral
    value. An all-zero probe scored 0.9995 (highly anomalous) against the
    13-feature geo-velocity checkpoint despite being intended as "clean,"
    which is a property of the probe, not the model — the same model scores
    genuine ordinary transactions correctly (see the 0.034% FPR on the real
    held-out test set, results/final_metrics.json). This row is the actual
    scaled feature vector `scripts/fifty_dollar_pass_check.py` produces for
    a real $50.00 fuel purchase — captured, not hand-invented.
    """
    seq = np.tile(
        np.array(
            [0.8581, 0.1968, 0.0, 0.0, 0.0, 0.0032, 0.0, 4.0, 0.6110, 0.4357, 0.7324, 1.0, 0.0],
            dtype=np.float32,
        ),
        (5, 1),
    )
    prob = client.predict(seq)
    assert 0.0 <= prob <= 1.0
    assert prob < THRESHOLD, f"Clean sequence scored {prob:.4f} — expected below {THRESHOLD}"


def test_fraud_pattern_returns_valid_probability(client):
    """A high-risk feature pattern returns a valid probability — verifies API, not model."""
    seq = np.zeros((5, 13), dtype=np.float32)
    # balance_drop_to_zero=1, amount_to_balance_ratio=1, amount_zscore=max
    seq[:, 4] = 1.0   # balance_drop_to_zero
    seq[:, 5] = 1.0   # amount_to_balance_ratio
    seq[:, 10] = 1.0  # amount_zscore (normalised max)
    prob = client.predict(seq)
    assert 0.0 <= prob <= 1.0


def test_single_sequence_shape(client):
    """API accepts [5, 13] input (auto-batched to [1, 5, 13])."""
    seq = np.random.rand(5, 13).astype(np.float32)
    prob = client.predict(seq)
    assert isinstance(prob, float)


def test_batch_predict(client):
    """API handles a batch of 8 sequences correctly."""
    batch = np.random.rand(8, 5, 13).astype(np.float32)
    probs = client.predict_batch(batch)
    assert len(probs) == 8
    assert all(0.0 <= p <= 1.0 for p in probs)


def test_invalid_shape_returns_422(client):
    """API rejects wrong feature count with HTTP 422."""
    bad_payload = {"instances": [[[0.0] * 10] * 5]}  # 10 features instead of 13
    r = requests.post(f"{BASE_URL}/v1/models/lstm:predict", json=bad_payload)
    assert r.status_code == 422


def test_inference_latency(client):
    """Single inference call must complete in under 1 second (target: < 200 ms)."""
    seq = np.random.rand(5, 13).astype(np.float32)
    start = time.perf_counter()
    client.predict(seq)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert elapsed_ms < 1000, f"Latency {elapsed_ms:.1f} ms exceeded 1000 ms limit"
    print(f"\nInference latency: {elapsed_ms:.1f} ms")
