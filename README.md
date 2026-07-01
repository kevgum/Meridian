# Meridian Sentinel

> **Real-Time Threat Detection & Mitigation Prototype**  
> Meridian Financial Services · ITW601 University Project  
> Hybrid LSTM Neural Network + Elastic SIEM fraud detection system  
> **Status:** `v1.0.0-prototype` — 14-day build complete, 35/35 acceptance tests passing

---

## What It Does

Meridian Sentinel detects financial fraud in real time by fusing two complementary engines:

- **LSTM Anomaly Detection** — stacked PyTorch LSTM trained on 6.3M PaySim transactions; flags behavioural deviations that rules miss
- **Elastic SIEM** — 4 rule-based detectors (high amount, geo-velocity, off-hours, watchlist merchant)
- **Hybrid Threat Scorer** — `lstm × 0.60 + siem × 0.40`; triggers automated playbook at ≥ 0.70
- **Playbook Engine** — locks account, writes Elasticsearch incident record, notifies analyst
- **RBAC** — 6 Elasticsearch roles enforcing least-privilege access
- **React SOC Dashboard** — live alert feed, investigation drawer, WCAG 2.2 AA compliant

**Model:** 98.4% accuracy · 1.54% FPR · p99 latency 28.5 ms  
**Tests:** 35/35 PASS — [`results/acceptance_test_report.md`](results/acceptance_test_report.md)  
**Security:** 0 FAIL / 6 low-info ZAP warnings — [`results/security_review.md`](results/security_review.md)

---

## Quick Start

```bash
git clone https://github.com/owenz4040/Meridaian.git
cd Meridaian
```

**Windows:**
```powershell
.\start.ps1
```

**Mac / Linux:**
```bash
chmod +x start.sh && ./start.sh
```

The script creates `.env`, builds all Docker images, starts Elasticsearch / Kibana / Logstash / lstm-serving, waits for health, and runs the test suite. First run takes 3–5 min (downloads PyTorch CPU layer).

Expected output:
```
  OK All tests passed

  LSTM Inference API  ->  http://localhost:8080/v1/models/lstm
  Kibana              ->  http://localhost:5601  (elastic / meridian123)
  Elasticsearch       ->  http://localhost:9200
  Logstash TCP        ->  localhost:5000
```

Bootstrap RBAC roles once after first start:
```bash
pip install elasticsearch==8.11.0
python scripts/bootstrap_rbac.py
```

> Full operational procedures (startup, RBAC, retraining, incident response, TLS): [docs/runbook.md](docs/runbook.md)  
> New to the project? Start with [onboarding.md](onboarding.md)

---

## Dashboard

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
```

Without a live stack the dashboard falls back to mock data automatically.  
See [docs/analyst-guide.md](docs/analyst-guide.md) for the alert triage workflow.

---

## Test Commands

All dev commands run inside the `dev` Docker container — no local Python needed:

```bash
# Full acceptance suite — 35 tests, requires full stack
docker compose --profile dev run --rm dev pytest tests/test_acceptance.py -v

# Unit-only — 32 tests, no stack required
docker compose --profile dev run --rm dev pytest tests/test_acceptance.py -v -m "not integration"

# SIEM rule engine — 22 tests
docker compose --profile dev run --rm dev pytest tests/test_siem_rules.py -v

# Hybrid scorer + playbook — 29 tests
docker compose --profile dev run --rm dev pytest tests/test_hybrid_scorer.py -v

# LSTM API smoke tests — requires lstm-serving
docker compose --profile dev run --rm dev pytest tests/test_inference_api.py -v

# RBAC integration — requires live ES + bootstrap_rbac.py
docker compose --profile dev run --rm dev pytest tests/test_rbac.py -v -m integration

# Latency benchmark (100 calls → results/latency_benchmark.json)
docker compose --profile dev run --rm dev python -m src.benchmark
```

---

## Making a Prediction

```bash
curl -X POST http://localhost:8080/v1/models/lstm:predict \
  -H "Content-Type: application/json" \
  -d '{
    "instances": [
      [[0.1,0.2,2.0,1.0,0.0,5732,3.0,8.0,0.5,0.3,0.8,1.2],
       [0.2,0.3,2.0,1.0,0.0,5732,4.0,9.0,0.6,0.3,0.9,1.3],
       [0.3,0.4,2.0,0.0,0.0,5812,5.0,10.0,0.7,0.4,1.0,1.5],
       [0.4,0.5,2.0,0.0,1.0,5732,6.0,11.0,0.8,0.5,1.1,1.8],
       [0.5,0.6,2.0,1.0,1.0,5732,7.0,12.0,0.9,0.6,1.2,2.1]]
    ]
  }'
```

Response: `{"predictions": [[0.74]]}` — score ≥ 0.90 = fraud (set via `DECISION_THRESHOLD` in `.env`).

---

## Documentation

### For operators and analysts

| File | What it covers |
|------|---------------|
| [onboarding.md](onboarding.md) | New team member setup — prerequisites, clone, env config, stack startup, RBAC bootstrap |
| [docs/runbook.md](docs/runbook.md) | Operational procedures — startup, stopping, health checks, retraining, incident response, TLS, common failures |
| [docs/analyst-guide.md](docs/analyst-guide.md) | SOC dashboard walkthrough — how to triage an alert, read threat scores, use the investigation drawer, CUST-18656 worked example |
| [docs/architecture.md](docs/architecture.md) | Full system design — component diagram, data flow, RBAC model, compliance control mapping (APRA / PCI DSS / Privacy Act) |

### For the ML pipeline

| File | What it covers |
|------|---------------|
| [docs/model-serving.md](docs/model-serving.md) | ONNX conversion, Dockerfile walkthrough, FastAPI inference API reference, latency benchmark results |
| [docs/training-notes.md](docs/training-notes.md) | Training history, the `pos_weight=773` collapse bug and fix, threshold tuning decisions across multiple runs |
| [docs/colab-guide.md](docs/colab-guide.md) | Step-by-step Google Colab training walkthrough — what to run, what to download, where files go locally |
| [docs/feature-engineering.md](docs/feature-engineering.md) | All 12 engineered features, sliding window construction, class imbalance strategy |

### For compliance and assessment

| File | What it covers |
|------|---------------|
| [compliance/control_mapping.md](compliance/control_mapping.md) | Full APRA CPS 234, PCI DSS v4.0, and Privacy Act 1988 control mapping with implementation status |
| [docs/requirements_traceability_matrix.md](docs/requirements_traceability_matrix.md) | US-01–US-12 user stories mapped to AT-1–AT-10 acceptance tests with pass/fail evidence |
| [docs/accessibility-audit.md](docs/accessibility-audit.md) | WCAG 2.2 Level AA audit results for the SOC dashboard — each criterion checked with evidence |
| [results/security_review.md](results/security_review.md) | Credential scan results and OWASP ZAP baseline report (0 FAIL / 6 low-info warnings) |
| [docs/retrospective.md](docs/retrospective.md) | 14-day build retrospective — what went well, what missed targets, lessons for production |

### Project planning (build artefacts)

| File | What it covers |
|------|---------------|
| [docs/PROJECT_BOARD.md](docs/PROJECT_BOARD.md) | Kanban board — all 14 days with status and key outputs |
| [docs/implementation-plan.md](docs/implementation-plan.md) | 14-day sprint plan with user stories, acceptance criteria, and day-by-day task breakdown |
| [docs/development-guide-2weeks.md](docs/development-guide-2weeks.md) | Original 2-week delivery guide used to scope the sprint |
| [docs/agent.md](docs/agent.md) | AI assistant persona, role definitions, and prompt templates used during the build |
| [docs/claude.md](docs/claude.md) | Guide to using Claude effectively as AI pair programmer — prompting patterns, error handling, day-by-day tips |

---

## Compliance

APRA CPS 234 · PCI DSS v4.0 · Australian Privacy Act 1988  
Full control mapping: [compliance/control_mapping.md](compliance/control_mapping.md)

---

## Release

Tagged `v1.0.0-prototype` on `main`.

| Evidence | File |
|----------|------|
| Acceptance tests (35/35 PASS) | [results/acceptance_test_report.md](results/acceptance_test_report.md) |
| Requirements traceability | [docs/requirements_traceability_matrix.md](docs/requirements_traceability_matrix.md) |
| Security review | [results/security_review.md](results/security_review.md) |
| Model card | [models/MODEL_CARD.md](models/MODEL_CARD.md) |
| Retrospective | [docs/retrospective.md](docs/retrospective.md) |
