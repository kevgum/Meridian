# Model Card — LSTMFraudDetector v1

## Model Details
| Field | Value |
|---|---|
| Model name | LSTMFraudDetector v1 |
| Architecture | Stacked LSTM (128 → 64 hidden units, 30% dropout) |
| Framework | PyTorch (training) / ONNX (inference) |
| Input shape | [batch, 5, 12] — 5-transaction sequence, 12 engineered features |
| Output | Scalar logit → sigmoid → anomaly probability [0, 1] |
| Decision threshold | 0.92 |
| Version | 1.0.0 |
| Training date | 2026-07-05 |

## Training Data
| Dataset | Rows | Fraud rate | Source |
|---|---|---|---|
| PaySim synthetic | 6,354,407 | ~0.13% | Kaggle (Lopez-Rojas 2016) |

Pre-processing: SHA-256 PII obfuscation, 12-feature engineering, MinMaxScaler normalisation,
sliding window sequences (length=5 per customer). Train/Val/Test split: 70/15/15 stratified.
Class imbalance handled with BCEWithLogitsLoss(pos_weight=1.0).

## Performance on Test Set
| Metric | Value | Target |
|---|---|---|
| Detection Accuracy | 98.8578% | ≥ 98.55% |
| False Positive Rate | 1.0969% | ≤ 0.50% |
| Precision | 6.9932% | — |
| Recall (TPR) | 63.8243% | — |
| F1-Score | 0.1261 | — |
| True Positives | 247 | — |
| False Positives | 3285 | — |

## Intended Use
- **Primary use:** Fraud detection component of the Meridian Sentinel hybrid threat scorer
- **Out-of-scope:** Sole decision-maker for account actions (requires hybrid scorer + analyst review)

## Known Limitations
1. Trained on PaySim synthetic data — not real Meridian transaction data
2. Mock features (geo_velocity_flag, session_entropy) use random values in this prototype
3. No SHAP/LIME explainability — planned for v2

## Compliance
| Control | Standard | Status |
|---|---|---|
| PII obfuscation | APRA CPS 234, Privacy Act | SHA-256 hash at ingestion |
| Model version record | PCI DSS v4.0 | This card + git tag |
| Bias documentation | APRA CPS 234 | Disaggregation in results/ |
| Human oversight | APRA CPS 234 | Analyst review required for all FLAGGED events |

## Artifact Locations
| Artifact | Path |
|---|---|
| PyTorch checkpoint (best) | models/lstm_checkpoint_best.pt |
| PyTorch final model | models/lstm_final.pt |
| ONNX export | models/serving/lstm_v1/lstm_fraud_detector.onnx |
| Final metrics | results/final_metrics.json |
| Confusion matrix | results/figures/confusion_matrix.png |
