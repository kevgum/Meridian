import logging
import numpy as np
import requests
from typing import Union

logger = logging.getLogger(__name__)


class LSTMInferenceClient:
    """
    Thin wrapper around the LSTM Inference API (ONNX Runtime + FastAPI).

    Usage:
        client = LSTMInferenceClient("http://localhost:8080")
        prob = client.predict(sequence)   # sequence: [5, 12] numpy array
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
            sequence: numpy array of shape [5, 12] or [1, 5, 12]

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
            sequences: numpy array of shape [batch_size, 5, 12]

        Returns:
            list[float]: anomaly probabilities for each sequence
        """
        payload = {"instances": sequences.tolist()}
        try:
            response = requests.post(self.predict_url, json=payload, timeout=self.timeout)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error("Batch inference API call failed: %s", e)
            raise

        return [float(p[0]) for p in response.json()["predictions"]]
