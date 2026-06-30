"""
Latency benchmark — 100 sequential inference calls against the LSTM serving API.

Usage:
    python -m src.benchmark

Requires the lstm-serving container to be running:
    docker-compose up -d lstm-serving

Outputs: results/latency_benchmark.json
"""

import json
import os
import time
import numpy as np
from src.inference_client import LSTMInferenceClient

BASE_URL = os.getenv("LSTM_SERVING_URL", "http://localhost:8080")
N_CALLS = 100


def run_benchmark() -> dict:
    client = LSTMInferenceClient(BASE_URL)

    if not client.health_check():
        raise RuntimeError(f"lstm-serving not reachable at {BASE_URL}. Run: docker-compose up -d lstm-serving")

    print(f"Running {N_CALLS} sequential inference calls against {BASE_URL} ...")
    latencies_ms = []

    for i in range(N_CALLS):
        seq = np.random.rand(5, 12).astype(np.float32)
        t0 = time.perf_counter()
        client.predict(seq)
        latencies_ms.append((time.perf_counter() - t0) * 1000)

    latencies_ms.sort()
    results = {
        "endpoint": BASE_URL,
        "n_calls": N_CALLS,
        "latency_ms": {
            "min": round(latencies_ms[0], 2),
            "max": round(latencies_ms[-1], 2),
            "mean": round(float(np.mean(latencies_ms)), 2),
            "p50": round(float(np.percentile(latencies_ms, 50)), 2),
            "p95": round(float(np.percentile(latencies_ms, 95)), 2),
            "p99": round(float(np.percentile(latencies_ms, 99)), 2),
        },
        "target_ms": 200,
        "p99_target_met": float(np.percentile(latencies_ms, 99)) < 200,
    }

    print(f"  min:  {results['latency_ms']['min']} ms")
    print(f"  mean: {results['latency_ms']['mean']} ms")
    print(f"  p95:  {results['latency_ms']['p95']} ms")
    print(f"  p99:  {results['latency_ms']['p99']} ms  (target < 200 ms: {results['p99_target_met']})")

    os.makedirs("results", exist_ok=True)
    with open("results/latency_benchmark.json", "w") as f:
        json.dump(results, f, indent=2)
    print("Saved: results/latency_benchmark.json")

    return results


if __name__ == "__main__":
    run_benchmark()
