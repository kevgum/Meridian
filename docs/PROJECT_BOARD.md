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

*(Empty — Day 9 complete)*

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

- [x] **US-04:** LSTM inference REST API — Day 6 (Sourav + Kevin)
  - [x] `Dockerfile.serving` — ONNX Runtime + FastAPI; auto-converts .pt → ONNX at startup
  - [x] `docker/convert_to_onnx.py` — conversion script bundled in container
  - [x] `docker-compose.yml` — lstm-serving + elasticsearch + kibana + logstash + healthchecks
  - [x] `src/inference_client.py` — REST client wrapper (predict + predict_batch)
  - [x] `tests/test_inference_api.py` — 7/7 smoke tests passing
  - [x] `results/latency_benchmark.json` — p99: 28.5 ms (target < 200 ms ✓)

- [x] **US-05:** SIEM detection rules — Day 7
  - [x] `src/siem/rule_engine.py` — ElasticSIEMCorrelator with 4 rules (amount, geo-velocity, off-hours, watchlist)
  - [x] Haversine geo-velocity helper (km/h computed from raw coordinates, not a flag)
  - [x] `ZoneInfo("Australia/Sydney")` for correct AEST/AEDT off-hours evaluation
  - [x] `watchlist/merchants.json` — 20 seed known-bad merchant IDs
  - [x] `logstash/pipelines/transaction_ingest.conf` — full ECS pipeline with SHA-256 PII hashing
  - [x] `tests/test_siem_rules.py` — 22/22 unit tests passing (no container required)

- [x] **US-06:** Automated playbooks — Day 8
  - [x] `src/siem/hybrid_scorer.py` — HybridThreatScorer with dual-threshold logic (HYBRID_THRESHOLD + LSTM_ALONE)
  - [x] `src/siem/playbook_engine.py` — PlaybookEngine: ES incident write, mock analyst notification, injected ES client for testability
  - [x] `tests/test_hybrid_scorer.py` — 29/29 unit tests passing (mocked ES, no container required)
  - [x] `results/e2e_test_cust18656.json` — CUST-18656 validation scenario documented
  - [x] Full suite: 60/60 tests passing (all days combined)

- [x] **US-11:** RBAC — Day 9
  - [x] `scripts/bootstrap_rbac.py` — creates 6 ES roles + 6 test users + scoped API key via elasticsearch-py; idempotent
  - [x] `tests/test_rbac.py` — 5 integration tests covering AT-9: analyst denied .kibana write, compliance officer read-only, engineer allowed
  - [x] `pytest.ini` — registers `integration` marker so RBAC tests are excluded from default unit-test run
  - [x] `docker-compose.yml` — Kibana session timeout 15 min (`xpack.security.session.idleTimeout=15m`)
  - [x] `scripts/generate_certs.sh` — self-signed TLS cert generation script (production hardening; not enforced in prototype)
  - [x] `.env.example` — added `ELASTIC_HOST` and `ELASTIC_API_KEY` variables
  - [x] `certs/.gitkeep` — tracks directory; private keys gitignored
  - [x] `docs/requirements_traceability_matrix.md` — US-01–US-11 → AT-1–AT-10 with gap analysis
  - [x] `compliance/control_mapping.md` — RBAC, session timeout, incident management, audit rows updated to ✅
