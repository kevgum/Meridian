# Onboarding Guide — Meridian Sentinel

> This guide gets a new team member from zero to a fully running local environment.  
> Read top to bottom. Every step matters.

---

## 1. What You're Building

Meridian Sentinel is a **hybrid real-time fraud detection system** for Meridian Financial Services. It is a university prototype (ITW601) that combines:

- A **stacked LSTM neural network** trained on 6.3M synthetic PaySim transactions — detects behavioural anomalies that rules cannot catch
- **Elastic SIEM** (Elasticsearch + Kibana + Logstash) — 4 rule-based detectors for high-value amounts, impossible geo-velocity, off-hours activity, and watchlist merchants
- A **Hybrid Threat Scorer** that blends both signals (`lstm × 0.60 + siem × 0.40`) and fires an automated playbook when the combined score is ≥ 0.70
- A **React analyst dashboard** (WCAG 2.2 AA) for alert triage and compliance reporting

**Compliance scope:** APRA CPS 234, PCI DSS v4.0, Australian Privacy Act 1988

---

## 2. Documentation Reading Order

Read these documents in order. Each one builds on the previous.

| # | Document | When to read | What you will learn |
|---|----------|-------------|---------------------|
| 1 | **This file** (`onboarding.md`) | First | How to set up your environment end to end |
| 2 | [`README.md`](README.md) | After onboarding | Quick reference for commands, ports, and troubleshooting |
| 3 | [`docs/architecture.md`](docs/architecture.md) | Before writing any code | Full system design, data flow diagrams, compliance control mapping |
| 4 | [`docs/implementation-plan.md`](docs/implementation-plan.md) | Before starting a task | 14-day sprint plan, user stories, and acceptance criteria per day |
| 5 | [`docs/PROJECT_BOARD.md`](docs/PROJECT_BOARD.md) | Before starting a task | Kanban board — what is done, in progress, and not started |
| 6 | [`docs/model-serving.md`](docs/model-serving.md) | If touching the LSTM API or Docker setup | How ONNX conversion works, Dockerfile walkthrough, API reference, latency results |
| 7 | [`docs/training-notes.md`](docs/training-notes.md) | If touching model training | History of training runs, the pos_weight collapse bug, threshold tuning decisions |
| 8 | [`docs/colab-guide.md`](docs/colab-guide.md) | Only if retraining the model | Step-by-step Colab walkthrough, what to download, where files go |
| 9 | [`compliance/control_mapping.md`](compliance/control_mapping.md) | Before any compliance or assessment work | Full APRA CPS 234, PCI DSS v4.0, and Privacy Act control mapping with status |
| 10 | [`docs/analyst-guide.md`](docs/analyst-guide.md) | Before using the SOC dashboard | How to triage alerts, read threat scores, and use the investigation drawer |
| 11 | [`docs/runbook.md`](docs/runbook.md) | Before operating the stack | Startup, RBAC bootstrap, retraining procedure, incident response, common failures |
| 12 | [`CLAUDE.md`](CLAUDE.md) | Only if using Claude as your AI assistant | AI session context, locked decisions, architecture summary |

**Minimum read for a new team member:** documents 1–5.  
**Before touching the ML pipeline:** add 6 and 7.  
**Before retraining:** add 8.  
**Before any compliance or assessment work:** add 9.  
**Before triaging alerts on the dashboard:** add 10.  
**Before operating the stack:** add 11.

---

## 3. Prerequisites

Install everything in this list before proceeding.

### Required

| Tool | Purpose | Install |
|------|---------|---------|
| Git | Version control | https://git-scm.com |
| Docker Desktop 4.x+ | Run all services | https://www.docker.com/products/docker-desktop |
| Python 3.11+ | Run tests and scripts locally | https://www.python.org/downloads |
| VS Code (recommended) | Code editor | https://code.visualstudio.com |

### Docker Desktop Settings

Open Docker Desktop → Settings → Resources and configure:

- **Memory:** minimum 4 GB (Elasticsearch needs at least 2 GB alone)
- **CPUs:** minimum 2
- **Disk image size:** minimum 20 GB (Docker images total ~2 GB)

Confirm Docker is running before proceeding:
```bash
docker --version        # should print Docker version 24.x or higher
docker compose version  # should print Docker Compose version 2.x or higher
```

**No local Python installation is required.** All tests and dev tools run inside a Docker container. If you want to run scripts outside Docker, install Python 3.11+ and run `pip install pytest requests numpy tzdata`.

---

## 4. Clone the Repository

```bash
git clone https://github.com/owenz4040/Meridaian.git
cd Meridaian
```

The `main` branch contains stable, reviewed code. Active development happens on feature branches (e.g., `feature/day6-docker-stack`).

To switch to the latest development branch:
```bash
git checkout feature/day6-docker-stack
```

---

## 5. Configure Your Environment

Copy the example environment file:
```bash
cp .env.example .env
```

The defaults work for local development without any changes. The `.env` file is gitignored — never commit it.

| Variable | Default | Notes |
|----------|---------|-------|
| `ELASTIC_PASSWORD` | `meridian123` | Change this for any shared or cloud environment |
| `LSTM_SERVING_URL` | `http://localhost:8080` | Internal Docker network uses `http://lstm-serving:8080` |
| `DECISION_THRESHOLD` | `0.90` | Fraud classification threshold (tuned in Day 5) |

---

## 6. Running the Stack

### One-command startup (recommended)

The startup scripts handle everything — no manual steps required.

**Windows (PowerShell):**
```powershell
.\start.ps1
```

**Mac / Linux:**
```bash
chmod +x start.sh
./start.sh
```

What the script does, in order:
1. Creates `.env` from `.env.example` if not present
2. Creates the `models/serving/lstm_v1/` output directory
3. Builds all Docker images (`lstm-serving` + `dev` toolbox)
4. Starts Elasticsearch, Kibana, Logstash, and the LSTM API
5. Polls until Elasticsearch and the LSTM API are healthy
6. Runs all 29 tests inside the `dev` container — no local Python needed
7. Prints service URLs

First run takes **5–8 minutes** (image downloads). Subsequent runs take **under 60 seconds**.

Expected output when everything is working:
```
▶ Stack is up

  LSTM Inference API  ->  http://localhost:8080/v1/models/lstm
  Kibana              ->  http://localhost:5601  (elastic / meridian123)
  Elasticsearch       ->  http://localhost:9200
  Logstash TCP        ->  localhost:5000
```

### Manual startup (step by step)

If you prefer to start services individually:

```bash
# Step 1 — create environment and required directories
cp .env.example .env
mkdir -p models/serving/lstm_v1

# Step 2 — build images
docker compose --profile dev build

# Step 3 — start all services
docker compose up -d elasticsearch kibana logstash lstm-serving

# Step 4 — wait for healthy (check status)
docker compose ps

# Step 5 — open Kibana
# Navigate to http://localhost:5601  (elastic / meridian123)
```

---

## 7. Verify Everything Works

Run the full test suite inside Docker — no local Python required:

```bash
docker compose --profile dev run --rm dev pytest tests/ -v
```

All 60 tests must pass:
```
tests/test_inference_api.py::test_health_check                                        PASSED
... (7 LSTM API tests)
tests/test_pipeline.py::test_pii_obfuscation                                          PASSED
tests/test_pipeline.py::test_feature_engineering_shapes_and_values                    PASSED
tests/test_siem_rules.py::TestRuleHighValue::test_triggers_above_threshold            PASSED
... (22 SIEM rule tests)
tests/test_hybrid_scorer.py::TestHybridFormula::test_formula_correct_mixed_scores     PASSED
... (29 hybrid scorer + playbook tests)
60 passed
```

To run only one suite:
```bash
# LSTM API tests (requires lstm-serving)
docker compose --profile dev run --rm dev pytest tests/test_inference_api.py -v

# Hybrid scorer + playbook tests (no services needed)
docker compose --profile dev run --rm dev pytest tests/test_hybrid_scorer.py -v

# SIEM rule tests (no services needed)
docker compose --profile dev run --rm dev pytest tests/test_siem_rules.py -v
```

If any test fails, check container logs:
```bash
docker compose logs lstm-serving --tail 50
```

---

## 8. Understanding the Model Input Format

The LSTM expects:
- **Shape:** `[batch_size, 5, 12]` — sequences of 5 transactions, each with 12 features
- **Endpoint:** `POST http://localhost:8080/v1/models/lstm:predict`
- **Threshold:** sigmoid output ≥ 0.90 → classified as fraud

The 12 features are:

| # | Feature | What It Measures |
|---|---------|-----------------|
| 1 | `amount_delta` | Deviation from customer rolling average |
| 2 | `balance_utilisation_ratio` | Sudden balance depletion signal |
| 3 | `channel_type_encoded` | PAYMENT=0 TRANSFER=1 CASH_OUT=2 DEBIT=3 CASH_IN=4 |
| 4 | `time_of_day_flag` | 0=business hours, 1=off-hours (before 08:00 or after 22:00 AEST) |
| 5 | `geo_velocity_flag` | 1 if location jump between transactions exceeds 500 km/h |
| 6 | `merchant_category_code` | MCC (label-encoded) |
| 7 | `transaction_frequency_1h` | Transaction count in last 1 hour |
| 8 | `transaction_frequency_24h` | Transaction count in last 24 hours |
| 9 | `cumulative_spend_ratio` | Session spend vs 30-day daily average |
| 10 | `beneficiary_risk_score` | Pre-computed risk of destination account |
| 11 | `amount_zscore` | Z-score vs customer history |
| 12 | `session_entropy` | Shannon entropy of merchant categories — high = unusual diversity |

---

## 9. Project Structure Explained

```
Meridaian/
│
├── config/model_config.yaml     ← LSTM hyperparameters. Change here, not in code.
│
├── docker/
│   └── convert_to_onnx.py       ← Runs inside container at startup. Converts .pt → .onnx.
│
├── docs/                        ← All project documentation
│   ├── architecture.md          ← System design, data flow, compliance mapping
│   ├── implementation-plan.md   ← 14-day task breakdown and acceptance criteria
│   ├── PROJECT_BOARD.md         ← Kanban board (Days 1–6 done, Day 7+ in progress)
│   └── training-notes.md        ← LSTM training history, pos_weight fix, threshold tuning
│
├── models/
│   ├── lstm_checkpoint_best.pt  ← Committed model weights (best val_acc epoch)
│   ├── lstm_final.pt            ← Final epoch weights
│   ├── serving/lstm_v1/         ← ONNX output (gitignored — generated at container start)
│   └── MODEL_CARD.md            ← Model version, training data, performance metrics
│
├── notebooks/                   ← Google Colab notebooks (run in Colab, not locally)
│   ├── 01_data_pipeline.ipynb   ← PaySim EDA + 12-feature engineering
│   ├── 02_lstm_model.ipynb      ← Training (20 epochs, WeightedRandomSampler)
│   └── 03_evaluation.ipynb      ← Evaluation + ONNX export
│
├── results/
│   ├── final_metrics.json       ← threshold=0.90, accuracy=98.4%, FPR=1.54%
│   ├── latency_benchmark.json   ← p99=28.5ms
│   └── figures/                 ← Confusion matrix, training curves
│
├── src/
│   ├── models/lstm_model.py     ← LSTMFraudDetector PyTorch class (input→128→64→1)
│   ├── serving/app.py           ← FastAPI app (ONNX Runtime inference)
│   ├── inference_client.py      ← Python REST wrapper for the API
│   └── benchmark.py             ← 100-call latency benchmark
│
├── tests/
│   ├── test_inference_api.py    ← 7 smoke tests (all passing as of Day 6)
│   └── test_acceptance.py       ← AT-1 through AT-10 (written on Day 12)
│
├── .env.example                 ← Copy to .env before running
├── docker-compose.yml           ← All services: elasticsearch, kibana, logstash, lstm-serving
├── Dockerfile.serving           ← LSTM container (Python 3.11, torch CPU, onnxruntime)
├── CLAUDE.md                    ← AI assistant context (read this if using Claude)
└── README.md                    ← Quick start guide
```

---

## 10. Key Technical Decisions

These decisions are final — do not re-open them without talking to the team:

| Decision | What Was Chosen | Why |
|----------|----------------|-----|
| Model framework | PyTorch (train) + ONNX Runtime (serve) | ONNX export produced in Day 5; avoids TF SavedModel conversion |
| Serving framework | FastAPI + uvicorn | Simpler than TF Serving; no TF dependency at inference time |
| ONNX conversion | Runs at container startup via `docker/convert_to_onnx.py` | Avoids committing large binary ONNX files to git |
| Decision threshold | 0.90 (sigmoid output) | Tuned in Day 5; reduces FPR to 1.54% at cost of recall (67.2%) |
| Fraud sampling | WeightedRandomSampler + pos_weight=1.0 | Fixes model collapse caused by original pos_weight=773 |
| SIEM score normalisation | 0/1/2/3+ rules → 0.0/0.33/0.67/1.00 | Linear scaling; matches architecture spec |
| Hybrid threshold | ≥ 0.70 triggers playbook | Matches project brief requirement |

---

## 11. Day-by-Day Build Status

| Day | Task | Status |
|-----|------|--------|
| 1 | GitHub infrastructure + CI/CD | ✅ Done |
| 2 | Data pipeline + feature engineering | ✅ Done |
| 3–4 | LSTM model training | ✅ Done |
| 5 | Evaluation (threshold tuning + ONNX export) | ✅ Done |
| 6 | ONNX Runtime + FastAPI serving (Docker) | ✅ Done — 7/7 tests pass, p99=28.5ms |
| 7 | Elastic SIEM + rule engine | ✅ Done — 22/22 tests pass, ECS Logstash pipeline live |
| 8 | Hybrid threat scorer + playbook engine | ✅ Done — 29/29 tests pass, CUST-18656 validated, LSTM_ALONE path added |
| 9 | RBAC + compliance mapping | ✅ Done — 6 roles, bootstrap script, compliance control mapping |
| 10–11 | React analyst dashboard | ✅ Done — live ES polling, WCAG 2.2 AA, session timeout, investigation drawer, Vercel deployed |
| 12 | Acceptance test suite (AT-1 through AT-10) | ✅ Done — 35 tests, 32/35 pass without Docker |
| 13 | Live integration tests + security review | ✅ Done — 35/35 PASS, ZAP 0 FAIL / 6 low-info WARN, `v1.0.0-prototype` tagged |
| 14 | README, analyst guide, runbook, retrospective | ✅ Done |

---

## 12. Notebooks (Google Colab)

The training notebooks run in Google Colab (GPU required for training, ~30 min per full run). They are not meant to run locally.

To run a notebook:
1. Open [Google Colab](https://colab.research.google.com)
2. File → Open notebook → GitHub → paste the repo URL
3. Select the notebook you want
4. Runtime → Change runtime type → GPU (T4)
5. Mount your Google Drive when prompted (for saving checkpoints)

After training, download the output files and place them in:
- `models/lstm_checkpoint_best.pt`
- `models/lstm_final.pt`
- `results/training_history.json`
- `results/final_metrics.json`
- `results/figures/`

---

## 13. Common Issues

**Port 9200 or 5601 already in use**

Another Elasticsearch or Kibana instance is running. Stop it, or change the host ports in `docker-compose.yml`.

**Elasticsearch exits immediately with exit code 137**

Out of memory. Increase Docker Desktop memory to at least 4 GB.

**ONNX model not found error in lstm-serving**

The `models/serving/lstm_v1/` directory must exist and be writable. Docker creates the ONNX file there at startup. If the file is corrupt (< 100 KB), delete it and restart the container:
```bash
# Windows
del models\serving\lstm_v1\lstm_fraud_detector.onnx
# Mac / Linux
rm models/serving/lstm_v1/lstm_fraud_detector.onnx

docker compose restart lstm-serving
```

**Tests fail with `ConnectionRefusedError`**

The `lstm-serving` container is not running or not yet healthy. Run `docker compose ps` and check its status.

---

## 14. Getting Help

- **Architecture questions** → read [docs/architecture.md](docs/architecture.md)
- **Task status** → read [docs/PROJECT_BOARD.md](docs/PROJECT_BOARD.md)
- **Training history + model decisions** → read [docs/training-notes.md](docs/training-notes.md)
- **Colab training walkthrough** → read [docs/colab-guide.md](docs/colab-guide.md)
- **ONNX conversion + serving infrastructure** → read [docs/model-serving.md](docs/model-serving.md)
- **Using Claude** → read [CLAUDE.md](CLAUDE.md) at the project root
- **Team communication** → Microsoft Teams (Meridian Sentinel channel)
