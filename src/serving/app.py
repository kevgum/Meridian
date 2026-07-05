import os
import logging
import numpy as np
import onnxruntime as ort
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MODEL_PATH = os.getenv("MODEL_PATH", "/models/lstm_fraud_detector.onnx")
THRESHOLD = float(os.getenv("DECISION_THRESHOLD", "0.92"))

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
    # Shape: [batch_size, sequence_length=5, features=12]
    instances: List[List[List[float]]]


class PredictResponse(BaseModel):
    predictions: List[List[float]]


@app.get("/v1/models/lstm")
def model_status():
    """Health check — returns AVAILABLE when model is loaded."""
    if session is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    return {
        "model_version_status": [
            {"version": "1", "state": "AVAILABLE", "threshold": THRESHOLD}
        ]
    }


@app.post("/v1/models/lstm:predict", response_model=PredictResponse)
def predict(request: PredictRequest):
    """
    Accepts a batch of 5-transaction sequences and returns anomaly probabilities.

    Input:  {"instances": [[[f1..f12], [f1..f12], [f1..f12], [f1..f12], [f1..f12]]]}
    Output: {"predictions": [[0.7412]]}
    """
    if session is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    try:
        arr = np.array(request.instances, dtype=np.float32)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Invalid input shape: {e}")

    if arr.ndim == 2:
        arr = arr[np.newaxis, ...]

    if arr.ndim != 3 or arr.shape[1] != 5 or arr.shape[2] != 12:
        raise HTTPException(
            status_code=422,
            detail=f"Expected shape [batch, 5, 12], got {list(arr.shape)}"
        )

    input_name = session.get_inputs()[0].name
    logits = session.run(None, {input_name: arr})[0]
    probs = (1.0 / (1.0 + np.exp(-logits))).tolist()

    if isinstance(probs[0], float):
        probs = [[p] for p in probs]

    return PredictResponse(predictions=probs)
