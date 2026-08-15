import logging
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import requests

logger = logging.getLogger(__name__)


@dataclass
class InferenceResult:
    """A batch of scores plus the provenance of the call that produced them.

    ``predict``/``predict_batch`` return bare floats and throw this away, which
    is fine for callers that only want the number. Anything that has to write
    an auditable record — which model, which call, how long — uses
    ``predict_batch_with_metadata`` and gets this instead.

    ``round_trip_ms`` is measured client-side and therefore includes HTTP and
    JSON overhead; ``latency_ms`` inside ``metadata`` is the server's own timing
    of the ONNX session alone. Both are kept because the gap between them is
    exactly the transport cost, which is worth being able to see.
    """

    scores: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)
    round_trip_ms: float = 0.0

    @property
    def request_id(self) -> str:
        """The server-assigned inference id, or an explicit marker if absent."""
        return str(self.metadata.get("request_id", "UNAVAILABLE"))

    @property
    def model_version(self) -> str:
        return str(self.metadata.get("model_version", "UNKNOWN"))

    @property
    def input_elements(self) -> int:
        """Total float32 values sent across the batch (batch x 5 x 13)."""
        return int(self.metadata.get("input_elements", 0))

    @property
    def output_elements(self) -> int:
        """Total scalars returned — one probability per sequence."""
        return int(self.metadata.get("output_elements", 0))


class LSTMInferenceClient:
    """
    Thin wrapper around the LSTM Inference API (ONNX Runtime + FastAPI).

    Usage:
        client = LSTMInferenceClient("http://localhost:8080")
        prob = client.predict(sequence)   # sequence: [5, 13] numpy array
    """

    def __init__(self, base_url: str = "http://localhost:8080", timeout: int = 5):
        self.predict_url = f"{base_url}/v1/models/lstm:predict"
        self.status_url = f"{base_url}/v1/models/lstm"
        self.timeout = timeout

    def health_check(self) -> bool:
        """Returns True if the inference API is up and model is loaded."""
        try:
            r = requests.get(self.status_url, timeout=self.timeout)
            return r.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def predict(self, sequence: np.ndarray) -> float:
        """
        Sends a single transaction sequence and returns anomaly probability.

        Args:
            sequence: numpy array of shape [5, 13] or [1, 5, 13]

        Returns:
            float: anomaly probability in [0.0, 1.0]
        """
        if sequence.ndim == 2:
            sequence = sequence[np.newaxis, ...]

        payload = {"instances": sequence.tolist()}
        try:
            response = requests.post(self.predict_url, json=payload, timeout=self.timeout)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error("Inference API call failed: %s", e)
            raise

        return float(response.json()["predictions"][0][0])

    def predict_batch(self, sequences: np.ndarray) -> list:
        """
        Sends a batch of sequences and returns a list of anomaly probabilities.

        Args:
            sequences: numpy array of shape [batch_size, 5, 13]

        Returns:
            list[float]: anomaly probabilities for each sequence
        """
        return self.predict_batch_with_metadata(sequences).scores

    def predict_batch_with_metadata(self, sequences: np.ndarray) -> InferenceResult:
        """Same call as ``predict_batch``, but keeps the response provenance.

        Args:
            sequences: numpy array of shape [batch_size, 5, 13] or [5, 13].

        Returns:
            InferenceResult: scores plus the server's metadata block and the
            client-measured round-trip time.

        The metadata block is absent when talking to an inference API older
        than the one in this repo. That is reported as an empty dict rather
        than fabricated values — ``InferenceResult.request_id`` then reads
        "UNAVAILABLE", which is a true statement about that deployment.
        """
        if sequences.ndim == 2:
            sequences = sequences[np.newaxis, ...]

        payload = {"instances": sequences.tolist()}
        started = time.perf_counter()
        try:
            response = requests.post(self.predict_url, json=payload, timeout=self.timeout)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error("Batch inference API call failed: %s", e)
            raise
        round_trip_ms = (time.perf_counter() - started) * 1000.0

        body = response.json()
        metadata = body.get("metadata") or {}
        if not metadata:
            logger.warning(
                "Inference API returned no metadata block — provenance for this "
                "call cannot be recorded (older serving build?)"
            )

        return InferenceResult(
            scores=[float(p[0]) for p in body["predictions"]],
            metadata=metadata,
            round_trip_ms=round(round_trip_ms, 3),
        )
