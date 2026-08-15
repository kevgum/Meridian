import os
import time
import uuid
import logging
from datetime import datetime, timezone

import numpy as np
import onnxruntime as ort
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MODEL_PATH = os.getenv("MODEL_PATH", "/models/lstm_fraud_detector.onnx")
THRESHOLD = float(os.getenv("DECISION_THRESHOLD", "0.90"))

# Reported on every prediction so a stored score can be traced back to the
# exact model that produced it. MODEL_VERSION is overridable at deploy time;
# the default tracks models/MODEL_CARD.md.
MODEL_NAME = os.getenv("MODEL_NAME", "LSTMFraudDetector")
MODEL_VERSION = os.getenv("MODEL_VERSION", "1.2.0")

session: ort.InferenceSession = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global session
    if not os.path.exists(MODEL_PATH):
        raise RuntimeError(f"ONNX model not found at {MODEL_PATH}")
    session = ort.InferenceSession(MODEL_PATH, providers=["CPUExecutionProvider"])
    logger.info("ONNX model loaded from %s", MODEL_PATH)
    yield
    session = None


app = FastAPI(title="Meridian LSTM Inference API", lifespan=lifespan)


class PredictRequest(BaseModel):
    # Shape: [batch_size, sequence_length=5, features=13]
    instances: List[List[List[float]]]


class InferenceMetadata(BaseModel):
    """Per-call provenance returned alongside the predictions.

    Exists so a score stored in Elasticsearch can be traced back to the exact
    model build and call that produced it. Previously the endpoint returned a
    bare probability, and a stored score had no way to answer "which model,
    when, how long did it take" after the fact.

    On ``input_elements``/``output_elements``: this is a tensor model, not a
    language model, so it has no tokens. The equivalent measure of how much
    data crossed the boundary is the element count of the tensors themselves —
    ``batch x 5 timesteps x 13 features`` in, one probability per sequence out.
    """

    request_id: str
    model_name: str
    model_version: str
    inference_timestamp: str
    latency_ms: float
    decision_threshold: float
    input_shape: List[int]
    input_elements: int
    output_shape: List[int]
    output_elements: int
    input_dtype: str


class PredictResponse(BaseModel):
    predictions: List[List[float]]
    # Optional so any existing client that validates this schema against an
    # older response keeps working; every live response populates it.
    metadata: Optional[InferenceMetadata] = None


@app.get("/v1/models/lstm")
def model_status():
    """Health check — returns AVAILABLE when model is loaded."""
    if session is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    return {
        "model_version_status": [
            {"version": "1", "state": "AVAILABLE", "threshold": THRESHOLD}
        ],
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "input_shape": [None, 5, 13],
        "input_elements_per_sequence": 5 * 13,
    }


@app.post("/v1/models/lstm:predict", response_model=PredictResponse)
def predict(request: PredictRequest):
    """
    Accepts a batch of 5-transaction sequences and returns anomaly probabilities.

    Input:  {"instances": [[[f1..f13], [f1..f13], [f1..f13], [f1..f13], [f1..f13]]]}
    Output: {"predictions": [[0.7412]], "metadata": {...}}

    The metadata block carries the request id, model version, server-side
    latency and tensor sizes — see InferenceMetadata.
    """
    if session is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    request_id = f"INF-{uuid.uuid4().hex[:16].upper()}"

    try:
        arr = np.array(request.instances, dtype=np.float32)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Invalid input shape: {e}")

    if arr.ndim == 2:
        arr = arr[np.newaxis, ...]

    if arr.ndim != 3 or arr.shape[1] != 5 or arr.shape[2] != 13:
        raise HTTPException(
            status_code=422,
            detail=f"Expected shape [batch, 5, 13], got {list(arr.shape)}"
        )

    # Timed around the ONNX session only, so the number reported is the model's
    # own compute cost and not the JSON parsing around it.
    input_name = session.get_inputs()[0].name
    started = time.perf_counter()
    logits = session.run(None, {input_name: arr})[0]
    latency_ms = (time.perf_counter() - started) * 1000.0

    probs = (1.0 / (1.0 + np.exp(-logits))).tolist()

    if isinstance(probs[0], float):
        probs = [[p] for p in probs]

    metadata = InferenceMetadata(
        request_id=request_id,
        model_name=MODEL_NAME,
        model_version=MODEL_VERSION,
        inference_timestamp=datetime.now(tz=timezone.utc).isoformat(),
        latency_ms=round(latency_ms, 3),
        decision_threshold=THRESHOLD,
        input_shape=list(arr.shape),
        input_elements=int(arr.size),
        output_shape=[len(probs), len(probs[0])],
        output_elements=int(len(probs) * len(probs[0])),
        input_dtype=str(arr.dtype),
    )

    logger.info(
        "inference request_id=%s model=%s:%s input_shape=%s input_elements=%d "
        "output_elements=%d latency_ms=%.3f",
        request_id, MODEL_NAME, MODEL_VERSION, list(arr.shape),
        arr.size, metadata.output_elements, latency_ms,
    )

    return PredictResponse(predictions=probs, metadata=metadata)
