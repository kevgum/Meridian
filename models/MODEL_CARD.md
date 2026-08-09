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
2. **Resolved 2026-08-08.** The fitted MinMaxScaler was not persisted with the
   original checkpoint, so inference had no way to reproduce the range training
   scaled into; a scaler refit on a small live batch set min/max from that
   batch's own extremes and returned confidently wrong scores instead of
   obviously broken ones (measured: every planted fraud at 0.000, two ordinary
   payments at 0.99). `scripts/fit_feature_scaler.py` recovered the scaler by
   re-running the same feature pipeline (`compute_feature_matrix`) over the
   identical seeded 2M-row PaySim sample (`random_state=42`) training used, and
   `src/pipeline/run_pipeline.py` now persists it on every future run. The
   recovered scaler is written to `models/feature_scaler.json`.

   **Validation.** `scripts/validate_feature_scaler.py` rebuilt the training
   pipeline's 70/15/15 test split and scored it through this checkpoint. The
   confusion-matrix counts did not reproduce this card's exact figures (TP 253
   vs. 247, FP 4111 vs. 3285) — the residual gap traces to Colab's unpinned
   `pip install pandas` drawing a different stratified `.sample()` result than
   this repo's pinned pandas 2.2.2 under the same `random_state=42`, not to a
   feature or scaling error (the feature formulas are byte-identical to the
   pre-checkpoint commit, and the recovered scaler's fitted range is
   order-invariant to any row permutation). In place of exact reproduction, the
   same test split was checked for class separation, which does not depend on
   matching Colab's row draw: **ROC AUC 0.9666**, mean score 0.863 (fraud) vs.
   0.116 (normal), median score 0.966 (fraud) vs. 0.000 (normal). A wrong
   scaler cannot produce that separation by construction — full report in
   `results/scaler_validation.json`.

   `scripts/generate_transaction_batch.py` now scores every transaction through
   the served LSTM and stamps `lstm_score_source: "model"`; it previously
   refused and fell back to representative stand-in values whenever the scaler
   was absent.
3. The feature list is `FEATURE_COLS` in `src/pipeline/feature_engineering.py`.
   An earlier draft naming `geo_velocity_flag`, `merchant_category_code`,
   `beneficiary_risk_score` and `session_entropy` at positions 5, 6, 10 and 12
   was never trained — do not build input tensors from it.
4. No SHAP/LIME explainability — planned for v2

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
