# Days 3–4 Training Notes — LSTMFraudDetector v1

## Environment
| Setting | Value |
|---|---|
| Platform | Google Colab (free tier) |
| GPU | Tesla T4 |
| PyTorch | 2.x |
| Dataset | PaySim real (`ealaxi/paysim1`) — stratified 2M-row sample |
| Reason for sampling | Full 6.3M rows caused OOM on Colab free tier (~12GB RAM limit) |

## Data Summary
| Split | Sequences | Fraud sequences | Fraud ratio |
|---|---|---|---|
| Train | ~1,167,000 | ~1,513 | ~0.13% |
| Val | ~250,000 | ~324 | ~0.13% |
| Test | ~250,000 | ~324 | ~0.13% |

**pos_weight used:** 773.41 (computed dynamically from train fraud ratio)

---

## Day 3 — Calibration Run

**Config:** 20% of training data, 5 epochs, LR=0.001, batch_size=512

| Epoch | Train Loss | Train Acc | Val Loss | Val Acc | Time |
|---|---|---|---|---|---|
| 1 | 1.3968 | 99.80% | 1.3903 | 99.87% | 7.67s |
| 2 | 1.3943 | 99.85% | 1.3855 | 99.87% | 8.02s |
| 3 | 1.3930 | 99.82% | 1.4014 | 99.87% | 6.54s |
| 4 | 1.3924 | 99.87% | 1.3854 | 99.87% | 7.25s |
| 5 | 1.3881 | 96.19% | 1.3894 | 99.87% | 7.26s |

**Outcome:** Model compiles and trains. Val accuracy 99.87% exceeds the ≥98.55% target.

---

## Day 4 — Full Training

**Config:** 100% training data, 10 epochs, LR=0.001, batch_size=512

| Epoch | Train Loss | Train Acc | Val Loss | Val Acc | Time |
|---|---|---|---|---|---|
| 01 | 1.3982 | 98.19% | 1.3905 | 99.87% | 23.9s |
| 02 | 1.4805 | 99.26% | 1.8215 | 99.87% | 22.2s |
| 03 | 1.9355 | 99.87% | 1.8927 | 99.87% | 22.0s |
| 04 | 1.9401 | 99.87% | 1.9972 | 99.87% | 24.2s |
| 05 | 1.9702 | 99.87% | 1.8998 | 99.87% | 23.0s |
| 06 | 1.9419 | 99.87% | 1.9177 | 99.87% | 21.9s |
| 07 | 1.8991 | 99.87% | 1.9924 | 99.87% | 22.6s |
| 08 | 1.9541 | 99.87% | 1.9554 | 99.87% | 22.6s |
| 09 | 1.9159 | 99.87% | 1.8945 | 99.87% | 22.9s |
| 10 | 1.9062 | 99.87% | 1.8707 | 99.87% | 22.4s |

**Best checkpoint:** Epoch 1 (val_acc = 99.87%)  
**Total training time:** ~230 seconds (~4 min)

---

## Observations & Notes for Day 5

### 1. Accuracy target MET — but accuracy alone is misleading here
Val accuracy of **99.87%** exceeds the ≥98.55% target. However, with only 0.13% fraud in the dataset, a model that predicts **every transaction as normal** would also achieve ~99.87% accuracy. This is the **accuracy paradox** for imbalanced classification.

**Val accuracy = 99.87% ≈ 1 − fraud_rate** — this match is not a coincidence and must be verified in Day 5 evaluation.

### 2. What Day 5 must confirm
The confusion matrix in `03_evaluation.ipynb` is critical. We need:
- **Recall (TPR) > 0** — model must be catching *some* actual fraud
- **FPR ≤ 0.50%** — low false alarm rate
- If recall = 0%: model has collapsed to always predicting normal → need to lower decision threshold (e.g. 0.1 instead of 0.5) or retrain with adjusted pos_weight

### 3. Loss increased after epoch 2
Train loss climbed from 1.40 → ~1.97 and plateaued. This is typical behaviour with very high pos_weight (~773) — the loss function aggressively penalises missed fraud cases, causing the model to oscillate. The `ReduceLROnPlateau` scheduler reduced LR after epoch 2 (patience=2).

### 4. Artefacts saved
| File | Location |
|---|---|
| Best checkpoint | `models/lstm_checkpoint_best.pt` (local + Drive) |
| Final model | `models/lstm_final.pt` (local + Drive) |
| Training history | `results/training_history.json` |
| Calibration results | `results/calibration_run_01.json` |
| Training curves plot | `results/figures/training_curves.png` |
