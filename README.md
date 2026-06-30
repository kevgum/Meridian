# Meridian Sentinel

> **Real-Time Threat Detection & Mitigation Prototype**  
> Meridian Financial Services · ITW601 University Project  
> Hybrid LSTM Neural Network + Elastic SIEM fraud detection system

---

## What It Does

Meridian Sentinel detects financial fraud in real time by fusing two complementary engines:

- **LSTM Anomaly Detection** — a stacked PyTorch LSTM trained on 6.3M PaySim transactions; flags statistical deviations that rule-based systems miss
- **Elastic SIEM** — 4 rule-based detectors (high amount, geo-velocity, off-hours, watchlist merchant)
- **Hybrid Threat Scorer** — blends both scores (`lstm × 0.60 + siem × 0.40`); triggers automated playbook at ≥ 0.70

**Model performance:** 98.4% accuracy · 1.54% FPR · p99 inference latency 28.5 ms

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

---

## Running Tests and Tools Without the Startup Script

All dev commands run inside the `dev` Docker container — no local Python needed:

```bash
# Full test suite (LSTM API + SIEM rule engine)
docker compose --profile dev run --rm dev pytest tests/ -v

# SIEM unit tests only (no running containers required)
docker compose --profile dev run --rm dev pytest tests/test_siem_rules.py -v

# LSTM API smoke tests only (lstm-serving must be running)
docker compose --profile dev run --rm dev pytest tests/test_inference_api.py -v

# Latency benchmark
docker compose --profile dev run --rm dev python -m src.benchmark

# Type checking
docker compose --profile dev run --rm dev mypy src/

# Linting
docker compose --profile dev run --rm dev flake8 src/ tests/
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
├── config/
│   └── model_config.yaml          # LSTM hyperparameters (epochs, features, thresholds)
├── docker/
│   └── convert_to_onnx.py         # .pt → .onnx conversion (runs at container startup)
├── docs/                          # Architecture, implementation plan, project board
├── logstash/pipelines/
│   └── transaction_ingest.conf    # Logstash ECS normalisation pipeline
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
│   └── figures/                   # training_curves.png, confusion_matrix.png
├── src/
│   ├── models/lstm_model.py       # LSTMFraudDetector PyTorch class
│   ├── serving/app.py             # FastAPI inference API
│   ├── siem/rule_engine.py        # ElasticSIEMCorrelator — 4 SIEM detection rules
│   ├── inference_client.py        # REST client wrapper
│   └── pipeline/                  # Feature engineering service
├── watchlist/
│   └── merchants.json             # Known-bad merchant IDs (SIEM Rule 4)
├── tests/
│   ├── test_inference_api.py      # 7 LSTM smoke tests (all passing)
│   ├── test_siem_rules.py         # 22 SIEM rule unit tests (all passing)
│   └── test_acceptance.py         # AT-1 through AT-10 (Day 12)
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
See [docs/architecture.md](docs/architecture.md) Section 8 for the full control mapping.
