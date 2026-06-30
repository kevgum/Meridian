"""
Runs at container startup: converts lstm_checkpoint_best.pt → lstm_fraud_detector.onnx
if the ONNX file is not already present at MODEL_PATH.
"""

import os
import sys
import yaml
import torch

CHECKPOINT_PATH = os.getenv("CHECKPOINT_PATH", "/checkpoint/lstm_checkpoint_best.pt")
MODEL_PATH = os.getenv("MODEL_PATH", "/models/lstm_fraud_detector.onnx")

if os.path.exists(MODEL_PATH):
    print(f"ONNX model already present at {MODEL_PATH} — skipping conversion.")
    sys.exit(0)

if not os.path.exists(CHECKPOINT_PATH):
    print(f"ERROR: checkpoint not found at {CHECKPOINT_PATH}")
    sys.exit(1)

sys.path.insert(0, "/app")

# Inline model definition to avoid src/ import complexity inside container
import torch.nn as nn

class LSTMFraudDetector(nn.Module):
    def __init__(self, input_size=12, hidden_size_1=128, hidden_size_2=64, dropout=0.30):
        super().__init__()
        self.lstm1 = nn.LSTM(input_size, hidden_size_1, batch_first=True)
        self.dropout = nn.Dropout(dropout)
        self.lstm2 = nn.LSTM(hidden_size_1, hidden_size_2, batch_first=True)
        self.fc = nn.Linear(hidden_size_2, 1)

    def forward(self, x):
        out, _ = self.lstm1(x)
        out = self.dropout(out)
        out, _ = self.lstm2(out)
        out = self.dropout(out)
        return self.fc(out[:, -1, :]).squeeze(-1)

with open("/app/model_config.yaml") as f:
    cfg = yaml.safe_load(f)

m = cfg["model"]
model = LSTMFraudDetector(
    input_size=m["input_features"],
    hidden_size_1=m["hidden_size_1"],
    hidden_size_2=m["hidden_size_2"],
    dropout=m["dropout"],
)
model.load_state_dict(torch.load(CHECKPOINT_PATH, map_location="cpu"))
model.eval()

os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
dummy = torch.zeros(1, 5, 12)

torch.onnx.export(
    model, dummy, MODEL_PATH,
    input_names=["transaction_sequence"],
    output_names=["anomaly_logit"],
    dynamic_axes={"transaction_sequence": {0: "batch_size"}, "anomaly_logit": {0: "batch_size"}},
    opset_version=17,
)

size_kb = os.path.getsize(MODEL_PATH) / 1024
print(f"ONNX exported: {MODEL_PATH}  ({size_kb:.0f} KB)")
