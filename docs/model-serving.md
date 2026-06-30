# Model Serving — ONNX Runtime + FastAPI

> This document explains how the trained LSTM model is packaged, converted, and served for real-time inference. It covers the full chain: PyTorch checkpoint → ONNX conversion → Docker container → FastAPI endpoint.

---

## 1. Why ONNX Runtime Instead of TF Serving

The original architecture spec listed TF Serving as the inference backend. This was changed on Day 6 for the following reason:

- The LSTM was trained in **PyTorch**, not TensorFlow
- Converting `.pt` → TF SavedModel requires `torch.onnx.export` + `tf2onnx` + `tf.saved_model.load` — three tools with version conflict risk
- **ONNX is PyTorch's native export format.** `torch.onnx.export` is a first-class PyTorch API, opset 17 is stable
- ONNX Runtime runs the exported model directly with no TensorFlow dependency
- FastAPI + uvicorn adds the REST layer with ~50 lines of Python

This reduces the serving stack from 4 components to 2 (onnxruntime + fastapi).

---

## 2. Why ONNX Conversion Happens at Container Startup

Two other approaches were considered and rejected:

| Approach | Problem |
|----------|---------|
| Commit `.onnx` file to git | ONNX files are ~500 KB binary. Git does not diff binaries; the file would grow the repo on every retrain and corrupt easily on paste/download |
| Convert in Colab, download `.onnx`, paste locally | Three attempts produced an 8.6 KB corrupt file — Drive export of binary ML files via the Colab download button is unreliable |

**Chosen approach:** The `.pt` checkpoint is committed to git (small enough, text-diffable weight format). The container converts it to ONNX at startup using `docker/convert_to_onnx.py`. If the ONNX file already exists in the volume mount, conversion is skipped.

---

## 3. Files Involved

| File | Role |
|------|------|
| `models/lstm_checkpoint_best.pt` | PyTorch checkpoint — committed to git; source of truth |
| `docker/convert_to_onnx.py` | Conversion script — runs inside container at startup |
| `Dockerfile.serving` | Container definition — installs torch CPU + onnxruntime |
| `docker-compose.yml` (lstm-serving service) | Mounts checkpoint + output directory; sets environment |
| `src/serving/app.py` | FastAPI app — loads ONNX, exposes predict endpoint |
| `src/inference_client.py` | Python REST wrapper for calling the API from other services |
| `models/serving/lstm_v1/` | ONNX output directory — gitignored, populated at container start |

---

## 4. How `docker/convert_to_onnx.py` Works

The script runs as the first step of the container's CMD. It:

1. Checks if `$MODEL_PATH` (default: `/models/lstm_fraud_detector.onnx`) already exists — if so, exits immediately (idempotent)
2. Checks that `$CHECKPOINT_PATH` (default: `/checkpoint/lstm_checkpoint_best.pt`) is present
3. Inlines the `LSTMFraudDetector` class definition (avoids `src/` import path issues inside the container)
4. Reads hyperparameters from `/app/model_config.yaml` — input_features, hidden sizes, dropout
5. Loads the checkpoint weights with `torch.load(..., map_location="cpu")`
6. Calls `torch.onnx.export` with:
   - `opset_version=17` — stable, widely supported
   - `dynamic_axes` on batch_size — allows variable batch sizes at inference time
   - `input_names=["transaction_sequence"]`, `output_names=["anomaly_logit"]`
7. Prints the output path and file size

Expected output when running for the first time:
```
ONNX exported: /models/lstm_fraud_detector.onnx  (482 KB)
```

If the ONNX file already exists:
```
ONNX model already present at /models/lstm_fraud_detector.onnx — skipping conversion.
```

---

## 5. How `Dockerfile.serving` Works

```dockerfile
FROM python:3.11-slim
WORKDIR /app

# Install torch (CPU-only, ~200 MB) for conversion + onnxruntime for serving
RUN pip install --no-cache-dir \
    torch==2.3.0+cpu \
    --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir \
    onnx==1.16.1 \
    onnxruntime==1.18.0 \
    fastapi==0.111.0 \
    "uvicorn[standard]==0.29.0" \
    numpy==1.26.4 \
    pydantic==2.7.1 \
    pyyaml==6.0.1

# Source files baked into the image at build time
COPY src/models/lstm_model.py   /app/lstm_model.py
COPY config/model_config.yaml   /app/model_config.yaml
COPY src/serving/app.py         /app/app.py
COPY docker/convert_to_onnx.py  /app/convert_to_onnx.py

ENV MODEL_PATH=/models/lstm_fraud_detector.onnx
ENV CHECKPOINT_PATH=/checkpoint/lstm_checkpoint_best.pt
ENV DECISION_THRESHOLD=0.90

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/v1/models/lstm')"

# Step 1: convert .pt → .onnx (skips if already done)
# Step 2: start FastAPI server
CMD ["sh", "-c", "python convert_to_onnx.py && uvicorn app:app --host 0.0.0.0 --port 8080"]
```

**Key design points:**
- `torch` is installed CPU-only to keep the image size manageable (no CUDA)
- `torch` is only needed for the one-time conversion step; it is not used at inference time (onnxruntime handles that)
- Source files are COPYed at build time, not mounted — the image is self-contained

---

## 6. Volume Mount Structure

```yaml
# docker-compose.yml — lstm-serving service
volumes:
  - ./models/lstm_checkpoint_best.pt:/checkpoint/lstm_checkpoint_best.pt:ro
  - ./models/serving/lstm_v1:/models
```

| Host path | Container path | Purpose |
|-----------|---------------|---------|
| `models/lstm_checkpoint_best.pt` | `/checkpoint/lstm_checkpoint_best.pt` | Read-only source checkpoint |
| `models/serving/lstm_v1/` | `/models/` | Read-write; ONNX file written here at startup |

The `models/serving/lstm_v1/` directory on the host must exist before running `docker compose up`. Create it if it doesn't:

```bash
# Windows
mkdir models\serving\lstm_v1

# Mac / Linux
mkdir -p models/serving/lstm_v1
```

---

## 7. FastAPI Inference API (`src/serving/app.py`)

### Startup

The app uses FastAPI's `asynccontextmanager` lifespan to load the ONNX session once at startup:

```python
session = ort.InferenceSession(MODEL_PATH, providers=["CPUExecutionProvider"])
```

If `MODEL_PATH` does not exist, the app raises `RuntimeError` and the container exits — Docker's healthcheck will report unhealthy.

### Endpoints

#### `GET /v1/models/lstm` — Health check

Returns the model status and current decision threshold.

```json
{
  "model_version_status": [
    {"version": "1", "state": "AVAILABLE", "threshold": 0.9}
  ]
}
```

Returns HTTP 503 if the ONNX session is not loaded.

#### `POST /v1/models/lstm:predict` — Inference

**Request body:**
```json
{
  "instances": [
    [
      [f1, f2, f3, f4, f5, f6, f7, f8, f9, f10, f11, f12],
      [f1, f2, f3, f4, f5, f6, f7, f8, f9, f10, f11, f12],
      [f1, f2, f3, f4, f5, f6, f7, f8, f9, f10, f11, f12],
      [f1, f2, f3, f4, f5, f6, f7, f8, f9, f10, f11, f12],
      [f1, f2, f3, f4, f5, f6, f7, f8, f9, f10, f11, f12]
    ]
  ]
}
```

- `instances` is a list of sequences (batch)
- Each sequence has **exactly 5 rows** (transactions) × **12 columns** (features)
- Values are `float32`

**Response:**
```json
{"predictions": [[0.7412]]}
```

- `predictions[i][0]` is the sigmoid anomaly probability for sequence `i`
- Values range from 0.0 (normal) to 1.0 (highly anomalous)
- The API does **not** apply the threshold — the caller decides what to do with the score

**Validation errors:**
- Wrong shape → HTTP 422 with shape details
- Non-numeric input → HTTP 422

### Sigmoid applied in-API

The ONNX model outputs raw logits (the PyTorch `Linear(64→1)` layer without sigmoid). The API applies sigmoid manually:

```python
probs = 1.0 / (1.0 + np.exp(-logits))
```

This is correct — `torch.onnx.export` exports the `forward()` method as-is, and the model's `forward()` returns logits (not probabilities).

---

## 8. Python Client (`src/inference_client.py`)

Use `LSTMInferenceClient` from other Python services to call the API without writing HTTP code:

```python
from src.inference_client import LSTMInferenceClient
import numpy as np

client = LSTMInferenceClient(base_url="http://localhost:8080")

# Single sequence
sequence = np.zeros((5, 12), dtype=np.float32)
score = client.predict(sequence)
# score → float e.g. 0.07

# Batch
sequences = [np.zeros((5, 12), dtype=np.float32) for _ in range(3)]
scores = client.predict_batch(sequences)
# scores → [0.07, 0.12, 0.74]
```

---

## 9. Build and Run Commands

```bash
# Build the image (do this once, or after changing Dockerfile.serving)
docker compose build lstm-serving

# Start the container
docker compose up -d lstm-serving

# Watch the startup logs (see ONNX conversion output)
docker compose logs lstm-serving -f

# Check health
docker compose ps
curl http://localhost:8080/v1/models/lstm

# Restart (e.g. after replacing the checkpoint)
docker compose restart lstm-serving

# Rebuild from scratch (clears the image layer cache)
docker compose build --no-cache lstm-serving
```

---

## 10. Replacing the Model

When a new training run produces better weights:

1. Copy the new checkpoint to `models/lstm_checkpoint_best.pt`
2. Delete the stale ONNX file so the container regenerates it:
   ```bash
   # Windows
   del models\serving\lstm_v1\lstm_fraud_detector.onnx
   # Mac / Linux
   rm models/serving/lstm_v1/lstm_fraud_detector.onnx
   ```
3. Restart the container:
   ```bash
   docker compose restart lstm-serving
   ```
4. The container will run `convert_to_onnx.py` again with the new weights
5. Verify the new ONNX file is ~482 KB and the API health check passes

---

## 11. Latency Benchmark Results (Day 6)

Run against `http://localhost:8080` on a local machine (Windows 11, Docker Desktop):

| Metric | Result | Target |
|--------|--------|--------|
| min | 3.99 ms | — |
| mean | 12.73 ms | — |
| p50 | ~12 ms | — |
| p95 | 27.76 ms | — |
| p99 | **28.5 ms** | < 200 ms ✅ |

Full results in `results/latency_benchmark.json`.  
Run the benchmark: `python -m src.benchmark`
