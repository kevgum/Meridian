# CLAUDE.md — Meridian Sentinel

> Read this file at the start of every Claude session. It contains everything you need to pick up the project without re-reading the full documentation.

---

## Role

**You are the Senior Software Engineer.** The user is the PM and Architect.

- Write complete, working code only — no stubs, no TODOs, no placeholder comments
- Follow the architecture in `docs/architecture.md` exactly
- All Python: PEP 8, full type annotations, docstrings on classes and public methods
- Never commit credentials or raw PII
- Use simple commit messages — no "Co-Authored-By" or AI attribution lines

---

## What This Project Is

**Meridian Sentinel** — hybrid real-time fraud detection prototype for Meridian Financial Services (ITW601 university project).

Two detection engines fused into one threat score:

```
threat_score = (lstm_score × 0.60) + (siem_score × 0.40)
```

- **≥ 0.70** → playbook fires (account lock + incident case + analyst notification)
- **< 0.70** → alert logged, MONITOR state

---

## Current State (as of Day 10 complete)

| Component | Status | Notes |
|-----------|--------|-------|
| LSTM model | ✅ Trained + committed | 98.4% acc, 1.54% FPR at threshold=0.90 |
| ONNX serving (FastAPI) | ✅ Running | p99=28.5ms, 7/7 smoke tests pass |
| Elastic SIEM stack | ✅ Done | Rule engine live, ECS Logstash pipeline, 22/22 tests pass |
| Hybrid scorer | ✅ Done | Dual-threshold logic, 60/60 tests pass |
| Playbook engine | ✅ Done | ES write + mock analyst notification, injected ES client |
| RBAC | ✅ Done | 6 roles, bootstrap script, AT-9 integration tests |
| React dashboard (Day 10) | ✅ Done | Vite+TS, 6 components, mock data, Vercel-ready |
| React dashboard (Day 11) | ⬜ Not started | Live ES polling, accessibility, re-deploy |
| Acceptance tests | ⬜ Not started | Day 12 |

Active branch: `feature/day10-dashboard`  
Main branch: `main`

---

## Architecture in One Page

```
Banking Channel Logs
        ↓
Logstash (ECS normalise + SHA-256 PII hash)
        ↓
Elasticsearch  ←──────────────────────────────────────────┐
        ↓                                                  │
Feature Engineering (Python Docker)                        │
  - 5-transaction sliding window per customer              │
  - 12 features → tensor [1, 5, 12]                       │
        ↓                                                  │
POST /v1/models/lstm:predict (ONNX Runtime + FastAPI)      │
  → anomaly_probability [0.0 – 1.0]                       │
        ↓                                                  │
SIEM Rule Engine (4 rules → siem_score)                   │
        ↓                                                  │
Hybrid Threat Scorer                                       │
  threat_score = lstm×0.60 + siem×0.40                    │
        ↓                    ↓                             │
   ≥ 0.70               < 0.70                            │
   Playbook              MONITOR                           │
   Engine  ─────────────────────────────────────────────→─┘
```

---

## Model Details

**Architecture:** `LSTMFraudDetector` in [src/models/lstm_model.py](src/models/lstm_model.py)

```
Input [batch, 5, 12]
  → LSTM(128, batch_first=True)
  → Dropout(0.30)
  → LSTM(64)
  → Dropout(0.30)
  → Linear(64 → 1)
  → sigmoid → anomaly_probability
```

**Training:** PyTorch, 20 epochs, WeightedRandomSampler, pos_weight=1.0  
**Serving:** ONNX Runtime + FastAPI — auto-converts `.pt → .onnx` at container startup  
**Config:** [config/model_config.yaml](config/model_config.yaml)  
**Decision threshold:** 0.90 (sigmoid output ≥ 0.90 = fraud)

**12 Features (in order):**
1. `amount_delta` — deviation from customer rolling average
2. `balance_utilisation_ratio` — newbalanceOrig / oldbalanceOrg
3. `channel_type_encoded` — PAYMENT=0, TRANSFER=1, CASH_OUT=2, DEBIT=3, CASH_IN=4
4. `time_of_day_flag` — 0=business hours, 1=off-hours (before 08:00 or after 22:00 AEST)
5. `geo_velocity_flag` — 1 if location jump > 500 km/h
6. `merchant_category_code` — MCC label-encoded
7. `transaction_frequency_1h`
8. `transaction_frequency_24h`
9. `cumulative_spend_ratio`
10. `beneficiary_risk_score`
11. `amount_zscore`
12. `session_entropy`

---

## SIEM Rules (Day 7 — complete)

Implemented in [src/siem/rule_engine.py](src/siem/rule_engine.py) as `ElasticSIEMCorrelator`. 22/22 unit tests passing.

| Rule | Condition | Severity |
|------|-----------|---------|
| Rule 1 | `amount > 10000` | HIGH |
| Rule 2 | Haversine geo-velocity > 500 km/h between consecutive transactions | HIGH |
| Rule 3 | Transaction time before 08:00 or after 22:00 AEST/AEDT | MEDIUM |
| Rule 4 | Merchant ID in `watchlist/merchants.json` | HIGH |

Each rule returns: `{rule_id, triggered: bool, severity: str, evidence: dict}`

SIEM score normalisation:
- 0 rules → 0.00
- 1 rule → 0.33
- 2 rules → 0.67
- 3+ rules → 1.00

**Event dict shape** (required fields for full rule evaluation):
```python
{
    "amount": float,              # Rule 1
    "lat": float, "lon": float,   # Rule 2 — current transaction coordinates
    "prev_lat": float, "prev_lon": float,  # Rule 2 — prior transaction
    "timestamp": str,             # Rules 2 + 3 — ISO 8601
    "prev_timestamp": str,        # Rule 2
    "merchant_id": str,           # Rule 4
}
```

**Windows note:** `pip install tzdata` required for `ZoneInfo("Australia/Sydney")`. Linux/Docker uses system IANA data automatically.

---

## Services and Ports

| Service | Port | Credentials |
|---------|------|-------------|
| LSTM Inference API | 8080 | — |
| Elasticsearch | 9200 | elastic / meridian123 |
| Kibana | 5601 | elastic / meridian123 |
| Logstash TCP | 5000 | — |

All credentials come from `.env` (copy from `.env.example`). Never hardcode.

---

## Key Files

| File | Purpose |
|------|---------|
| [config/model_config.yaml](config/model_config.yaml) | All LSTM hyperparameters |
| [src/models/lstm_model.py](src/models/lstm_model.py) | LSTMFraudDetector class |
| [src/serving/app.py](src/serving/app.py) | FastAPI inference API |
| [src/inference_client.py](src/inference_client.py) | REST wrapper (predict / predict_batch) |
| [docker/convert_to_onnx.py](docker/convert_to_onnx.py) | .pt → .onnx conversion script |
| [Dockerfile.serving](Dockerfile.serving) | LSTM container definition |
| [docker-compose.yml](docker-compose.yml) | Full stack orchestration |
| [models/lstm_checkpoint_best.pt](models/lstm_checkpoint_best.pt) | Best training checkpoint |
| [models/MODEL_CARD.md](models/MODEL_CARD.md) | Model version + performance |
| [results/final_metrics.json](results/final_metrics.json) | threshold=0.90 evaluation |
| [results/latency_benchmark.json](results/latency_benchmark.json) | p99=28.5ms benchmark |
| [docs/PROJECT_BOARD.md](docs/PROJECT_BOARD.md) | Kanban — what's done vs in progress |
| [docs/architecture.md](docs/architecture.md) | Full system architecture |
| [docs/training-notes.md](docs/training-notes.md) | Training history + decisions |
| [docs/model-serving.md](docs/model-serving.md) | ONNX conversion + Docker serving — full technical reference |
| [docs/colab-guide.md](docs/colab-guide.md) | Step-by-step Colab training + download instructions |
| [compliance/control_mapping.md](compliance/control_mapping.md) | APRA CPS 234, PCI DSS v4.0, Privacy Act control mapping with status |
| [src/siem/rule_engine.py](src/siem/rule_engine.py) | ElasticSIEMCorrelator — 4 SIEM rules + score normalisation |
| [src/siem/hybrid_scorer.py](src/siem/hybrid_scorer.py) | HybridThreatScorer — blends LSTM + SIEM, dual-threshold verdict |
| [src/siem/playbook_engine.py](src/siem/playbook_engine.py) | PlaybookEngine — incident record, ES write, mock analyst notification |
| [watchlist/merchants.json](watchlist/merchants.json) | Known-bad merchant IDs (Rule 4 seed data, 20 entries) |
| [logstash/pipelines/transaction_ingest.conf](logstash/pipelines/transaction_ingest.conf) | Full ECS pipeline — SHA-256 PII hash, field mapping, ES output |
| [results/e2e_test_cust18656.json](results/e2e_test_cust18656.json) | CUST-18656 end-to-end validation output (Day 8) |
| [scripts/bootstrap_rbac.py](scripts/bootstrap_rbac.py) | Creates 6 ES roles + test users + API key — run once after stack starts |
| [scripts/generate_certs.sh](scripts/generate_certs.sh) | Self-signed TLS cert generation for Elasticsearch (production hardening) |
| [tests/test_rbac.py](tests/test_rbac.py) | RBAC integration tests — AT-9 coverage (requires live ES) |
| [docs/requirements_traceability_matrix.md](docs/requirements_traceability_matrix.md) | US-01–US-11 → AT-1–AT-10 traceability matrix |
| [frontend/src/data/mockData.ts](frontend/src/data/mockData.ts) | All Day 10 mock data — KPIs, CUST-18656 transactions, SIEM result, incident, chart history |
| [frontend/src/types/index.ts](frontend/src/types/index.ts) | TypeScript interfaces for dashboard |
| [frontend/src/components/](frontend/src/components/) | 6 React components: TopBar, TransactionFeed, DetectionPanel, AlertQueue, HybridChart, ComplianceBadges |
| [frontend/vercel.json](frontend/vercel.json) | Vercel SPA rewrite rule |

---

## Decisions Already Made — Do Not Re-Open

| Decision | Chosen |
|----------|--------|
| Serving framework | ONNX Runtime + FastAPI (not TF Serving) |
| ONNX source | Auto-converted from `.pt` at container startup |
| Decision threshold | 0.90 |
| pos_weight | 1.0 (WeightedRandomSampler handles class balance) |
| LSTM weights | `lstm_checkpoint_best.pt` (best val_acc checkpoint, not final epoch) |
| Hybrid threshold | 0.70 |
| LSTM_ALONE trigger | lstm_score >= 0.70 fires playbook even with siem_score=0 (covers CUST-18656 scenario) |
| RBAC approach | bootstrap_rbac.py creates roles via ES API (not Kibana UI) — reproducible and version-controlled |
| TLS enforcement | TLS 1.3 config + cert script provided; not enforced in Docker prototype (would require updating all service URLs and healthchecks) |
| Frontend framework | Vite + React + TypeScript (not Create React App — CRA is unmaintained since 2023) |
| Tailwind version | Tailwind CSS v4 — uses @tailwindcss/vite plugin, no tailwind.config.js, @import "tailwindcss" in CSS |
| Day 10 data | All mock (hardcoded) — Day 11 wires to live Elasticsearch polling |

---

## Known Issues and History

- Old checkpoints trained with `pos_weight=773` caused all-normal collapse (val_acc=99.87% = 1−fraud_rate). Fixed in Day 5 with WeightedRandomSampler + pos_weight=1.0.
- ONNX files are gitignored — they are generated at container startup, not committed.
- The `models/serving/lstm_v1/` directory must exist locally for Docker volume mount to work.

---

## Test Commands

```bash
# Dashboard dev server (Day 10+)
cd frontend && npm run dev          # http://localhost:5173

# Dashboard production build
cd frontend && npm run build

# Deploy to Vercel (requires vercel login first)
cd frontend && npx vercel --prod

# Full test suite (all 60 tests — requires lstm-serving healthy)
docker compose --profile dev run --rm dev pytest tests/ -v

# Day 8 unit tests only (no services required — mocked ES)
docker compose --profile dev run --rm dev pytest tests/test_hybrid_scorer.py -v

# SIEM rule engine tests (no services required)
docker compose --profile dev run --rm dev pytest tests/test_siem_rules.py -v

# LSTM API smoke tests (lstm-serving must be running)
docker compose --profile dev run --rm dev pytest tests/test_inference_api.py -v

# Latency benchmark (100 calls → results/latency_benchmark.json)
python -m src.benchmark

# Full stack up
docker compose up -d

# Check container health
docker compose ps

# View logs
docker compose logs lstm-serving --tail 50
docker compose logs elasticsearch --tail 30
```

---

## Compliance Scope

- **APRA CPS 234** — information security capability, incident management, audit trail
- **PCI DSS v4.0** — network isolation, AES-256, TLS 1.3, RBAC, immutable logs
- **Australian Privacy Act 1988** — SHA-256 PII hashing at Logstash ingestion; raw values never stored

Full control mapping: [docs/architecture.md](docs/architecture.md) Section 8
