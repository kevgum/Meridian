# Meridian Sentinel — Local Kanban Board

Instead of relying on an external GitHub UI, this local markdown file serves as the project's issue tracker and Kanban board. You can move tasks between the columns as you progress through the 14-day execution plan.

## 📋 BACKLOG

- [ ] **US-01:** Load & preprocess PaySim (Data Epic)
- [ ] **US-02:** Log ingestion to Elasticsearch (Data Epic)
- [ ] **US-03:** Train LSTM ≥95% accuracy (LSTM Epic)
- [ ] **US-04:** LSTM inference REST API (LSTM Epic)
- [ ] **US-05:** SIEM detection rules (SIEM Epic)
- [ ] **US-06:** Automated playbooks (SIEM Epic)
- [ ] **US-07:** Kibana dashboard (Dashboard Epic)
- [ ] **US-08:** Compliance audit log export (Compliance Epic)
- [ ] **US-09:** README & deployment guide (Docs Epic)
- [ ] **US-10:** Control mapping document (Compliance Epic)

---

## 🏃 IN PROGRESS

- [x] **US-04:** LSTM inference REST API — Day 6 (Sourav + Kevin)
  - [x] `Dockerfile.serving` — ONNX Runtime + FastAPI; auto-converts .pt → ONNX at startup
  - [x] `docker/convert_to_onnx.py` — conversion script bundled in container
  - [x] `docker-compose.yml` — lstm-serving + feature-engineering + healthchecks
  - [x] `src/inference_client.py` — REST client wrapper (predict + predict_batch)
  - [x] `tests/test_inference_api.py` — 7/7 smoke tests passing
  - [x] `results/latency_benchmark.json` — p99: 28.5 ms (target < 200 ms ✓)

---

## 👀 REVIEW

*(Move items here when testing or waiting for PR merge to `dev`)*

*(Empty)*

---

## ✅ DONE

- [x] Initial Repository & Infrastructure Setup (Day 1)
- [x] **US-01:** Load & preprocess PaySim — feature engineering pipeline (Day 2)
- [x] **US-02:** PII obfuscation + Elasticsearch ingestion scaffold (Day 2)
- [x] **US-03:** Train LSTM ≥95% accuracy — Days 3–5 (Sourav lead)
  - [x] `src/models/lstm_model.py` — LSTMFraudDetector architecture
  - [x] `config/model_config.yaml` — hyperparameters (pos_weight=1.0, epochs=20)
  - [x] `notebooks/02_lstm_model.ipynb` — calibration + full training (Colab)
  - [x] `notebooks/03_evaluation.ipynb` — evaluation + ONNX export (Colab)
  - [x] Calibration run (20% subset, 5 epochs) → `results/calibration_run_01.json`
  - [x] Full training (20 epochs, pos_weight=1.0 + WeightedRandomSampler) → `results/training_history.json`, `results/figures/training_curves.png`
  - [x] Evaluated on test set at threshold=0.90 → accuracy 98.4%, recall 67.2%, FPR 1.54%
  - [x] ONNX export → `models/serving/lstm_v1/lstm_fraud_detector.onnx` (Drive only — gitignored)
  - [x] `models/MODEL_CARD.md` written and committed
