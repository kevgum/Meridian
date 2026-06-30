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

## 2. Prerequisites

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

### Python packages for local testing

```bash
pip install pytest requests numpy
```

---

## 3. Clone the Repository

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

## 4. Configure Your Environment

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

## 5. Running the Stack

### Step 1 — Build the LSTM serving container

This only needs to be done once (or when `Dockerfile.serving` changes):
```bash
docker compose build lstm-serving
```

Build takes 3–5 minutes on first run (downloads PyTorch CPU + ONNX Runtime). You will see progress output. Wait until you see `Successfully built`.

### Step 2 — Start the LSTM API

```bash
docker compose up -d lstm-serving
```

On first start, the container converts `models/lstm_checkpoint_best.pt` → `models/serving/lstm_v1/lstm_fraud_detector.onnx`. This takes ~15 seconds. You will see in the logs:

```
ONNX exported: /models/lstm_fraud_detector.onnx  (482 KB)
INFO: Uvicorn running on http://0.0.0.0:8080
```

Check it is healthy:
```bash
docker compose ps
# lstm-serving should show: Up (healthy)

curl http://localhost:8080/v1/models/lstm
# Expected: {"status": "ok", "model": "lstm_fraud_detector", "threshold": 0.9}
```

### Step 3 — Start the Elastic SIEM stack

```bash
docker compose up -d elasticsearch kibana logstash
```

Elasticsearch takes 30–60 seconds to become healthy. Monitor it:
```bash
docker compose logs elasticsearch -f
# Wait for: "Active license is now [BASIC]; Security is enabled"
```

### Step 4 — Verify all services

```bash
docker compose ps
```

All four containers should show `Up (healthy)` or `Up`:

| Container | Port | Status |
|-----------|------|--------|
| lstm-serving | 8080 | `Up (healthy)` |
| elasticsearch | 9200 | `Up (healthy)` |
| kibana | 5601 | `Up` |
| logstash | 5000 | `Up` |

### Step 5 — Open Kibana

Navigate to http://localhost:5601 in your browser.

Login: `elastic` / `meridian123`

---

## 6. Verify the LSTM API Works

Run the smoke test suite:
```bash
python -m pytest tests/test_inference_api.py -v
```

All 7 tests must pass:
```
test_health_check                           PASSED
test_clean_transaction_low_score            PASSED
test_fraud_pattern_returns_valid_probability PASSED
test_single_sequence_shape                  PASSED
test_batch_predict                          PASSED
test_invalid_shape_returns_422              PASSED
test_inference_latency                      PASSED
7 passed in ~9s
```

If any test fails, check container logs:
```bash
docker compose logs lstm-serving --tail 50
```

---

## 7. Understanding the Model Input Format

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

## 8. Project Structure Explained

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

## 9. Key Technical Decisions

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

## 10. Day-by-Day Build Status

| Day | Task | Status |
|-----|------|--------|
| 1 | GitHub infrastructure + CI/CD | ✅ Done |
| 2 | Data pipeline + feature engineering | ✅ Done |
| 3–4 | LSTM model training | ✅ Done |
| 5 | Evaluation (threshold tuning + ONNX export) | ✅ Done |
| 6 | ONNX Runtime + FastAPI serving (Docker) | ✅ Done — 7/7 tests pass, p99=28.5ms |
| 7 | Elastic SIEM + rule engine | 🔄 In Progress |
| 8 | Hybrid threat scorer + playbook engine | ⬜ Not started |
| 9 | RBAC + compliance mapping | ⬜ Not started |
| 10–11 | React analyst dashboard | ⬜ Not started |
| 12 | Acceptance test suite (AT-1 through AT-10) | ⬜ Not started |
| 13 | Security review + documentation | ⬜ Not started |
| 14 | Final handover + deployment guide | ⬜ Not started |

---

## 11. Notebooks (Google Colab)

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

## 12. Common Issues

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

## 13. Getting Help

- **Architecture questions** → read [docs/architecture.md](docs/architecture.md)
- **Task status** → read [docs/PROJECT_BOARD.md](docs/PROJECT_BOARD.md)
- **Training history + model decisions** → read [docs/training-notes.md](docs/training-notes.md)
- **Colab training walkthrough** → read [docs/colab-guide.md](docs/colab-guide.md)
- **ONNX conversion + serving infrastructure** → read [docs/model-serving.md](docs/model-serving.md)
- **Using Claude** → read [CLAUDE.md](CLAUDE.md) at the project root
- **Team communication** → Microsoft Teams (Meridian Sentinel channel)
