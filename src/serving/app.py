import json
import os
import time
import uuid
import logging
from collections import deque
from datetime import datetime, timezone

import numpy as np
import onnxruntime as ort
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from typing import Any, Deque, Dict, List, Optional

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

# Rolling log of the inferences this process has served, newest last.
#
# Scope, stated plainly because it is easy to over-read: this is the *model
# server's* view. It sees tensors, never transactions — there is no customer id,
# amount or merchant at this layer, because none of that is sent to the model.
# It is also in-process memory, so it starts empty on every container restart
# and covers only this replica.
#
# The durable, transaction-level record is the meridian-audit-* Elasticsearch
# index written by src/observability/audit.py, which correlates each of these
# request_ids back to the transaction that caused it.
_LOG_CAPACITY = 200
_INFERENCE_LOG: Deque[Dict[str, Any]] = deque(maxlen=_LOG_CAPACITY)
_TOTALS: Dict[str, Any] = {
    "requests_served": 0,
    "sequences_scored": 0,
    "input_elements": 0,
    "output_elements": 0,
    "started_at": None,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global session
    if not os.path.exists(MODEL_PATH):
        raise RuntimeError(f"ONNX model not found at {MODEL_PATH}")
    session = ort.InferenceSession(MODEL_PATH, providers=["CPUExecutionProvider"])
    _TOTALS["started_at"] = datetime.now(tz=timezone.utc).isoformat()
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


def _normalise_shape(raw: list) -> list:
    """Turn an ONNX shape into plain JSON.

    ONNX reports a dynamic axis as its symbolic name (``"batch_size"``) rather
    than a number. Those become ``None`` so the shape reads as a list of
    dimensions with the variable one marked, instead of mixing ints and
    strings.
    """
    return [d if isinstance(d, int) else None for d in raw]


def _element_count(shape: list) -> int:
    """Elements in one sequence — the product of the fixed dimensions.

    Dynamic axes (batch) are skipped, so this answers "per sequence", which is
    the number that stays constant regardless of how many are sent at once.
    """
    count = 1
    for d in shape:
        if isinstance(d, int) and d > 0:
            count *= d
    return count


@app.get("/v1/models/lstm")
def model_status(limit: int = 20, pretty: Optional[str] = None):
    """Model status, tensor sizes, and a log of what this server has scored.

    Tensor shapes are read from the loaded ONNX graph rather than hardcoded, so
    they cannot drift away from the model actually being served.

    Args:
        limit: how many recent inferences to include (newest first). Use 0 to
               omit the log and return status only.
        pretty: return indented text/plain instead of compact JSON. Follows
                Elasticsearch's own ``?pretty`` convention, including accepting
                the bare flag with no value — a browser shows this endpoint as
                one unreadable line otherwise, which makes it useless for
                inspecting the inference log by eye. Accepts ``?pretty``,
                ``?pretty=true`` and ``?pretty=1``; anything else is false.
    """
    if session is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    inp = session.get_inputs()[0]
    out = session.get_outputs()[0]
    in_shape = _normalise_shape(inp.shape)
    out_shape = _normalise_shape(out.shape)

    body = {
        "model_version_status": [
            {"version": "1", "state": "AVAILABLE", "threshold": THRESHOLD}
        ],
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,

        # Kept at the top level for backwards compatibility with anything
        # already reading them; the full picture is under "io".
        "input_shape": in_shape,
        "input_elements_per_sequence": _element_count(in_shape),

        "io": {
            "input": {
                "name": inp.name,
                "shape": in_shape,
                "dtype": inp.type,
                "elements_per_sequence": _element_count(in_shape),
                "layout": "5 timesteps x 13 engineered features",
            },
            "output": {
                "name": out.name,
                "shape": out_shape,
                "dtype": out.type,
                "elements_per_sequence": _element_count(out_shape),
                "layout": "one logit per sequence; sigmoid applied at serve "
                          "time to give an anomaly probability in [0, 1]",
            },
            # Stated explicitly because "token count" is the question this
            # endpoint gets asked, and the honest answer is that the concept
            # does not apply: tokens are a language-model unit. The comparable
            # measure for a tensor model is how many values cross the
            # boundary, which is what the counts above are.
            "note": "This is a tensor model, not a language model, so it has "
                    "no tokens. The equivalent measure is tensor elements: "
                    f"{_element_count(in_shape)} float32 values in per "
                    f"sequence, {_element_count(out_shape)} out.",
        },

        "inference_log": {
            "totals": dict(_TOTALS),
            "capacity": _LOG_CAPACITY,
            "returned": min(limit, len(_INFERENCE_LOG)) if limit > 0 else 0,
            "available": len(_INFERENCE_LOG),
            # Newest first — the opposite of insertion order, because the
            # question this answers is almost always "what just happened".
            "recent": list(reversed(_INFERENCE_LOG))[:limit] if limit > 0 else [],
            "scope": "In-process memory for this container only: it resets on "
                     "restart and holds the last "
                     f"{_LOG_CAPACITY} calls. The model server sees tensors, "
                     "not transactions - there is no customer id, amount or "
                     "merchant at this layer because none is sent to the "
                     "model. For the transaction-level record, query the "
                     "meridian-audit-* Elasticsearch index by correlation_id; "
                     "each audit entry carries the request_id shown here.",
        },
    }

    # "" is what a bare ?pretty flag arrives as.
    if pretty is not None and pretty.lower() in ("", "true", "1", "yes"):
        return PlainTextResponse(json.dumps(body, indent=2))
    return body


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

    # Keep a rolling record so /v1/models/lstm can show what this server has
    # actually scored. Probabilities are rounded for display; the authoritative
    # values are the ones returned above and stored in Elasticsearch.
    scored = [round(float(p[0]), 4) for p in probs]
    _INFERENCE_LOG.append({
        "request_id": request_id,
        "timestamp": metadata.inference_timestamp,
        "input_shape": list(arr.shape),
        "input_elements": int(arr.size),
        "output_shape": [len(probs), len(probs[0])],
        "output_elements": metadata.output_elements,
        "latency_ms": round(latency_ms, 3),
        "anomaly_probabilities": scored,
        "assessment": [
            "ANOMALY" if s >= THRESHOLD else "NORMAL" for s in scored
        ],
    })
    _TOTALS["requests_served"] += 1
    _TOTALS["sequences_scored"] += len(probs)
    _TOTALS["input_elements"] += int(arr.size)
    _TOTALS["output_elements"] += metadata.output_elements

    return PredictResponse(predictions=probs, metadata=metadata)
