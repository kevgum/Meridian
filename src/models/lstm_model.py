import torch
import torch.nn as nn
from typing import Tuple
import numpy as np


class LSTMFraudDetector(nn.Module):
    """
    Stacked LSTM for transaction anomaly detection.
    Input:  [batch, seq_len=5, features=12]
    Output: scalar logit per sample (apply sigmoid for probability)
    """

    def __init__(
        self,
        input_size: int = 12,
        hidden_size_1: int = 128,
        hidden_size_2: int = 64,
        dropout: float = 0.30,
    ):
        super().__init__()
        self.lstm1 = nn.LSTM(input_size, hidden_size_1, batch_first=True)
        self.dropout = nn.Dropout(dropout)
        self.lstm2 = nn.LSTM(hidden_size_1, hidden_size_2, batch_first=True)
        self.fc = nn.Linear(hidden_size_2, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out, _ = self.lstm1(x)
        out = self.dropout(out)
        out, _ = self.lstm2(out)
        out = self.dropout(out)
        # Take the last timestep's hidden state → single logit
        return self.fc(out[:, -1, :]).squeeze(-1)

    def predict_proba(self, x: torch.Tensor) -> torch.Tensor:
        """Convenience method: returns sigmoid probability (no gradient)."""
        with torch.no_grad():
            return torch.sigmoid(self.forward(x))


def build_model(cfg: dict) -> "LSTMFraudDetector":
    m = cfg["model"]
    return LSTMFraudDetector(
        input_size=m["input_features"],
        hidden_size_1=m["hidden_size_1"],
        hidden_size_2=m["hidden_size_2"],
        dropout=m["dropout"],
    )


def compute_pos_weight(y: np.ndarray) -> float:
    """Returns BCEWithLogitsLoss pos_weight from label array."""
    fraud_rate = y.mean()
    if fraud_rate == 0:
        return 1.0
    return float((1.0 - fraud_rate) / fraud_rate)
