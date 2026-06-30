# Meridian Sentinel

> **Real-Time Threat Detection & Mitigation Prototype**  
> Meridian Financial Services · ITW601 University Project  
> Hybrid LSTM Neural Network + Elastic SIEM fraud detection system  
> **Status:** `v1.0.0-prototype` — 14-day build complete, 35/35 acceptance tests passing

---

## What It Does

Meridian Sentinel detects financial fraud in real time by fusing two complementary engines:

- **LSTM Anomaly Detection** — a stacked PyTorch LSTM trained on 6.3M PaySim transactions; flags statistical deviations that rule-based systems miss
- **Elastic SIEM** — 4 rule-based detectors (high amount, geo-velocity, off-hours, watchlist merchant)
- **Hybrid Threat Scorer** — blends both scores (`lstm × 0.60 + siem × 0.40`); triggers automated playbook at ≥ 0.70
- **Playbook Engine** — locks the account, opens an Elasticsearch incident record, and notifies the analyst when the playbook fires
- **RBAC** — 6 Elasticsearch roles (security_analyst, senior_security_engineer, ml_operations, compliance_officer, system_administrator, read_only_auditor) enforce least-privilege access
- **React SOC Dashboard** — live alert feed, LSTM/SIEM/hybrid score breakdown, investigation drawer, WCAG 2.2 AA compliant

**Model performance:** 98.4% accuracy · 1.54% FPR · p99 inference latency 28.5 ms  
**Acceptance tests:** 35/35 PASS (full suite, live Docker stack, 3.43s) — see [`results/acceptance_test_report.md`](results/acceptance_test_report.md)  
**Security review:** Credential scan clean, OWASP ZAP baseline 0 FAIL / 6 low-info WARN — see [`results/security_review.md`](results/security_review.md)

**More documentation:**
- [docs/analyst-guide.md](docs/analyst-guide.md) — how a SOC analyst triages alerts on the dashboard
- [docs/runbook.md](docs/runbook.md) — operational procedures (startup, RBAC bootstrap, retraining, incident response)
- [docs/retrospective.md](docs/retrospective.md) — 14-day build retrospective
- [onboarding.md](onboarding.md) — new team member setup guide

---

## Prerequisites

Install these before doing anything else:

| Tool | Version | Download |
|------|---------|----------|
| Git | Any | https://git-scm.com |
| Docker Desktop | 4.x+ | https://www.docker.com/products/docker-desktop |
| Python | 3.11+ | https://www.python.org/downloads |

Verify Docker is running:
```bash
docker --version
docker compose version
```

---

## Quick Start — one command

The entire stack runs in Docker. **No local Python installation required.**

```bash
git clone https://github.com/owenz4040/Meridaian.git
cd Meridaian
```

**Windows (PowerShell):**
```powershell
.\start.ps1
```

**Mac / Linux:**
```bash
chmod +x start.sh && ./start.sh
```

The script handles everything:
1. Creates `.env` from `.env.example`
2. Creates the required `models/serving/lstm_v1/` output directory
3. Builds all Docker images (3–5 min on first run — downloads PyTorch CPU)
4. Starts Elasticsearch, Kibana, Logstash, and the LSTM serving container
5. Waits for all services to be healthy
6. Runs the full test suite inside Docker (29 tests — no local Python needed)
7. Prints service URLs

Expected final output:
```
  OK All tests passed

  LSTM Inference API  ->  http://localhost:8080/v1/models/lstm
  Kibana              ->  http://localhost:5601  (elastic / meridian123)
  Elasticsearch       ->  http://localhost:9200
  Logstash TCP        ->  localhost:5000
```

After the stack is up, bootstrap RBAC roles and test users (one-time, idempotent):
```bash
pip install elasticsearch==8.11.0
python scripts/bootstrap_rbac.py
```

---

## Running the Dashboard

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173 — polls live Elasticsearch via Vite proxy
```

Production build:
```bash
npm run build
npx vercel --prod     # requires `vercel login` first
```

Without a live stack the dashboard falls back to mock data automatically — see the top bar status indicator ("Connected to live Elasticsearch" vs "Demo mode — mock data").

See [docs/analyst-guide.md](docs/analyst-guide.md) for how to use the dashboard to triage an alert.

---

## Running Tests and Tools Without the Startup Script

All dev commands run inside the `dev` Docker container — no local Python needed:

```bash
# Full acceptance suite — 35 tests (AT-1 through AT-10), requires full stack
docker compose --profile dev run --rm dev pytest tests/test_acceptance.py -v

# Unit-only acceptance tests — 32 tests, no Docker stack required
docker compose --profile dev run --rm dev pytest tests/test_acceptance.py -v -m "not integration"

# SIEM rule engine tests — 22 tests (no running containers required)
docker compose --profile dev run --rm dev pytest tests/test_siem_rules.py -v

# Hybrid scorer + playbook engine tests — 29 tests (mocked ES, no container required)
docker compose --profile dev run --rm dev pytest tests/test_hybrid_scorer.py -v

# LSTM API smoke tests — 7 tests (lstm-serving must be running)
docker compose --profile dev run --rm dev pytest tests/test_inference_api.py -v

# RBAC integration tests (requires live ES + scripts/bootstrap_rbac.py already run)
docker compose --profile dev run --rm dev pytest tests/test_rbac.py -v -m integration

# Latency benchmark
docker compose --profile dev run --rm dev python -m src.benchmark
```

---

## Making a Prediction

Send a POST request with a sequence of 5 transactions × 12 features:

```bash
curl -X POST http://localhost:8080/v1/models/lstm:predict \
  -H "Content-Type: application/json" \
  -d '{
    "instances": [
      [[0.1, 0.2, 2.0, 1.0, 0.0, 5732, 3.0, 8.0, 0.5, 0.3, 0.8, 1.2],
       [0.2, 0.3, 2.0, 1.0, 0.0, 5732, 4.0, 9.0, 0.6, 0.3, 0.9, 1.3],
       [0.3, 0.4, 2.0, 0.0, 0.0, 5812, 5.0, 10.0, 0.7, 0.4, 1.0, 1.5],
       [0.4, 0.5, 2.0, 0.0, 1.0, 5732, 6.0, 11.0, 0.8, 0.5, 1.1, 1.8],
       [0.5, 0.6, 2.0, 1.0, 1.0, 5732, 7.0, 12.0, 0.9, 0.6, 1.2, 2.1]]
    ]
  }'
```

Response:
```json
{"predictions": [[0.74]]}
```

A score ≥ 0.90 is classified as fraud (configurable via `DECISION_THRESHOLD` in `.env`).

---

## Running the Latency Benchmark

```bash
python -m src.benchmark
```

Runs 100 sequential inference calls and reports min/mean/p50/p95/p99 latency. Saves results to `results/latency_benchmark.json`. Target: p99 < 200 ms.

---

## Project Structure

```
Meridaian/
├── compliance/
│   └── control_mapping.md         # APRA CPS 234, PCI DSS v4.0, Privacy Act control mapping
├── config/
│   └── model_config.yaml          # LSTM hyperparameters (epochs, features, thresholds)
├── docker/
│   └── convert_to_onnx.py         # .pt → .onnx conversion (runs at container startup)
├── docs/                          # Architecture, analyst guide, runbook, retrospective
├── frontend/                      # React + TypeScript + Tailwind SOC dashboard (Vite)
│   └── src/components/            # TopBar, TransactionFeed, DetectionPanel, AlertQueue,
│                                   # HybridChart, ComplianceBadges, InvestigateDrawer
├── logstash/pipelines/
│   └── transaction_ingest.conf    # Logstash ECS normalisation + SHA-256 PII hash pipeline
├── models/
│   ├── lstm_checkpoint_best.pt    # Best model checkpoint (committed)
│   ├── lstm_final.pt              # Final epoch checkpoint
│   ├── serving/lstm_v1/           # ONNX file output directory (gitignored)
│   └── MODEL_CARD.md              # Model version, performance, threshold
├── notebooks/
│   ├── 01_data_pipeline.ipynb     # PaySim EDA + feature engineering (Google Colab)
│   ├── 02_lstm_model.ipynb        # LSTM training (Google Colab)
│   └── 03_evaluation.ipynb        # Evaluation at multiple thresholds + ONNX export
├── results/
│   ├── final_metrics.json         # threshold=0.90, accuracy=98.4%, FPR=1.54%
│   ├── latency_benchmark.json     # p99=28.5ms
│   ├── acceptance_test_report.md  # AT-1–AT-10 evidence, 35/35 PASS
│   ├── security_review.md         # Credential scan + OWASP ZAP baseline results
│   └── figures/                   # training_curves.png, confusion_matrix.png
├── scripts/
│   └── bootstrap_rbac.py          # Creates 6 ES roles, test users, API key, Kibana token
├── src/
│   ├── models/lstm_model.py       # LSTMFraudDetector PyTorch class
│   ├── serving/app.py             # FastAPI inference API
│   ├── siem/rule_engine.py        # ElasticSIEMCorrelator — 4 SIEM detection rules
│   ├── siem/hybrid_scorer.py      # HybridThreatScorer — blends LSTM + SIEM
│   ├── siem/playbook_engine.py    # PlaybookEngine — incident record + analyst notify
│   ├── inference_client.py        # REST client wrapper
│   └── pipeline/                  # Feature engineering service
├── watchlist/
│   └── merchants.json             # Known-bad merchant IDs (SIEM Rule 4)
├── tests/
│   ├── test_inference_api.py      # 7 LSTM smoke tests
│   ├── test_siem_rules.py         # 22 SIEM rule unit tests
│   ├── test_hybrid_scorer.py      # 29 hybrid scorer + playbook tests
│   ├── test_rbac.py               # RBAC integration tests
│   └── test_acceptance.py         # AT-1 through AT-10 — 35/35 PASS
├── .env.example                   # Environment variable template
├── docker-compose.yml             # Full stack orchestration
├── Dockerfile.serving             # LSTM inference container
├── CLAUDE.md                      # AI assistant context (start here if using Claude)
└── onboarding.md                  # Team onboarding guide
```



## Stopping the Stack

```bash
# Stop all containers (keeps data)
docker compose down

# Stop and delete Elasticsearch data volume (full reset)
docker compose down -v
```

---

## Troubleshooting

**Container fails to start (no logs):**
```bash
docker compose logs lstm-serving --tail 50
```

**ONNX file missing / corrupt:**
```bash
# Delete and let the container regenerate it
rm models/serving/lstm_v1/lstm_fraud_detector.onnx
docker compose restart lstm-serving
```

**Elasticsearch not healthy after 60s:**
```bash
docker compose logs elasticsearch --tail 30
# Common fix: increase Docker Desktop memory to at least 4 GB
```

**Port 8080 already in use:**
```bash
# Check what's on the port
netstat -ano | findstr :8080          # Windows
lsof -i :8080                         # Mac/Linux
# Then change the host port in docker-compose.yml: "8081:8080"
```

---

## Team

| Role | Name |
|------|------|
| Security Engineer | Kevin Mugambi |

---

## Compliance

APRA CPS 234 · PCI DSS v4.0 · Australian Privacy Act 1988  
See [compliance/control_mapping.md](compliance/control_mapping.md) and [docs/architecture.md](docs/architecture.md) Section 8 for the full control mapping.

---

## Release

Tagged `v1.0.0-prototype` on `main` — Day 13. Full evidence trail:

| Evidence | File |
|----------|------|
| Acceptance tests (35/35 PASS) | [results/acceptance_test_report.md](results/acceptance_test_report.md) |
| Requirements traceability (US-01–US-11 → AT-1–AT-10) | [docs/requirements_traceability_matrix.md](docs/requirements_traceability_matrix.md) |
| Security review (credential scan + OWASP ZAP) | [results/security_review.md](results/security_review.md) |
| Accessibility audit (WCAG 2.2 AA) | [docs/accessibility-audit.md](docs/accessibility-audit.md) |
| Model card | [models/MODEL_CARD.md](models/MODEL_CARD.md) |
| Retrospective | [docs/retrospective.md](docs/retrospective.md) |
