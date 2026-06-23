# Meridian Sentinel — 14-Day Implementation Plan

> **Project:** Real-Time Threat Detection & Mitigation for Meridian Financial Services  
> **Stack:** Python · PyTorch/TensorFlow · Elastic SIEM · React/Tailwind · Docker · GitHub  
> **Team:** Maria Angel (PM) · Sourav Das (ML Engineer) · Kevin Mugambi (Security Engineer)  
> **Budget:** AUD $84,000 | **Target Accuracy:** ≥98.55% | **Target FPR:** ≤0.50%

---

## Week 1 — Core Infrastructure, Data Pipeline & LSTM Engine

---

### Day 1 — GitHub Infrastructure & CI/CD Scaffolding
**Owner:** All three | **Phase:** Project Initiation

**Objectives:**
- Create the `meridian-sentinel` private GitHub repository
- Establish branch strategy: `main` (production) and `dev` (active development)
- Set up automated CI/CD safeguards so every pull request to `dev` is linted and type-checked

**Tasks:**
1. Create GitHub repo `meridian-sentinel` (private)
2. Create branches: `main` and `dev`
3. Add `.github/workflows/ci.yml` — triggers on PRs to `dev`, runs `flake8` (syntax) and `mypy` (type checking)
4. Add `.gitignore` for Python, Jupyter, Docker, and secrets
5. Add `README.md` stub with project title and team names
6. Add `CODEOWNERS` file assigning each directory to the relevant engineer
7. Set up Jira board with epics: Data Pipeline, LSTM Detection, SIEM Integration, Dashboard, Compliance, Testing
8. Create initial product backlog in Jira matching US-01 through US-21 from the project report
9. Hold kick-off stand-up (15 min) — confirm tooling access for all team members

**Deliverables:**
- `meridian-sentinel` repo with `main` / `dev` branches live
- CI pipeline passing on empty commit
- Jira board populated

**Acceptance:** CI badge green; all three team members have push access to `dev`

---

### Day 2 — Synthetic Data Ingestion & Feature Engineering Pipeline
**Owner:** Sourav (lead), Kevin | **Phase:** Data Pipeline

**Objectives:**
- Download and validate the PaySim dataset (6.3 M transactions)
- Build the feature engineering pipeline that transforms raw logs into LSTM-ready sequences

**Tasks:**
1. Open Google Colab notebook — `01_data_pipeline.ipynb`
2. Load PaySim dataset; validate schema fields: `amount`, `oldbalanceOrg`, `newbalanceOrig`, `type`, `nameOrig`, `nameDest`, `isFraud`, `step` (timestamp proxy)
3. Perform exploratory data analysis — class imbalance check, null counts, channel distribution
4. Write `feature_engineering.py`:
   - Aggregate transactions into **sequences of 5 per customer** (sliding window)
   - Engineer **12 features**: `amount_delta`, `balance_utilisation_ratio`, `channel_type_encoded`, `time_of_day_flag` (business hours / off-hours), `geo_velocity_flag`, `merchant_category_code`, `transaction_frequency_1h`, `transaction_frequency_24h`, `cumulative_spend_ratio`, `beneficiary_risk_score`, `amount_zscore`, `session_entropy`
5. Apply PII obfuscation: hash `nameOrig` and `nameDest` with SHA-256 at ingestion
6. Write train/validation/test split (70/15/15 stratified on `isFraud`)
7. Export processed sequences to `/data/processed/` as `.npy` arrays
8. Commit `feature_engineering.py` to `dev` via PR — peer review by Kevin
9. Update Jira: US-02 data preparation sub-task complete

**Deliverables:**
- `01_data_pipeline.ipynb` (Colab)
- `src/feature_engineering.py`
- Processed `.npy` sequence arrays in `/data/processed/`

**Acceptance:** Feature script runs end-to-end without errors; class ratio logged; no raw PII in output files

---

### Day 3 — LSTM Model Architecture Design & Baseline Training Run
**Owner:** Sourav (lead) | **Phase:** LSTM Development

**Objectives:**
- Implement the stacked LSTM architecture defined in Assessment 2
- Run a first calibration training on a 20% data subset to establish a baseline before full GPU spend

**Tasks:**
1. Create `02_lstm_model.ipynb` in Colab
2. Implement `LSTMFraudDetector` class in PyTorch:
   - Input layer: 12 features × sequence length 5
   - LSTM Layer 1: 128 units, `batch_first=True`
   - LSTM Layer 2: 64 units
   - Dropout: 30% between layers
   - Dense output: sigmoid activation → anomaly probability [0,1]
3. Write `model_config.yaml` with all hyperparameters (learning rate, batch size, epochs, dropout, hidden units) for reproducibility
4. Run **calibration training** on 20% subset — 5 epochs — record baseline accuracy and loss
5. Log baseline metrics to `results/calibration_run_01.json`
6. Commit `src/models/lstm_model.py` and `model_config.yaml` to `dev`
7. Maria: update risk register — RM-04 (model performance risk) status after baseline result

**Deliverables:**
- `src/models/lstm_model.py`
- `config/model_config.yaml`
- `results/calibration_run_01.json`

**Acceptance:** Model compiles; calibration run completes in <30 min on Colab GPU; baseline accuracy logged

---

### Day 4 — Full LSTM Training, Loss Tracking & Hyperparameter Tuning
**Owner:** Sourav (lead), Maria | **Phase:** LSTM Development

**Objectives:**
- Run full training on 100% of the dataset for 10 epochs
- Track live metrics and hit the ≥95% accuracy target by epoch 3 (as demonstrated in prototype)

**Tasks:**
1. Switch Colab runtime to GPU (T4 or A100)
2. Run full training loop — 10 epochs — on complete PaySim training split
3. Training loop must log per-epoch: `train_loss`, `train_accuracy`, `val_loss`, `val_accuracy`
4. Generate **live training plot** (matplotlib): Training Loss per Epoch + Training Accuracy per Epoch with a dashed red 95% target baseline line
5. If accuracy < 90% by epoch 5 — apply hyperparameter adjustments: increase learning rate warm-up, reduce batch size, add label smoothing
6. Save best checkpoint to `models/lstm_checkpoint_best.pt`
7. Save final model to `models/lstm_final.pt` and export Keras `.h5` equivalent
8. Export training history to `results/training_history.json`
9. Commit all outputs; Sourav opens PR to `dev` — Kevin reviews

**Deliverables:**
- `models/lstm_final.pt` + `models/lstm_checkpoint_best.pt`
- `results/training_history.json`
- Training plots saved as `results/figures/training_curves.png`

**Acceptance:** Val accuracy ≥ 95% by epoch 10; loss curve shows convergence; model file < 500 MB

---

### Day 5 — Evaluation, Confusion Matrix & Model Export
**Owner:** Sourav (lead), Maria | **Phase:** LSTM Development

**Objectives:**
- Evaluate the trained model on the held-out test set
- Confirm detection accuracy ≥ 98.55% and FPR ≤ 0.50%
- Export the model for TensorFlow Serving inference

**Tasks:**
1. Create `03_evaluation.ipynb`
2. Run inference on test split (never seen during training)
3. Generate `sklearn` classification report: Precision, Recall, F1, FPR per class
4. Generate **Confusion Matrix** — plot with seaborn heatmap; label axes as Actual / Predicted with Normal / Fraud categories
5. Disaggregate confusion matrix by: transaction channel type and amount range (bias check per RM-09)
6. Record final metrics in `results/final_metrics.json`:
   - Detection Accuracy: target ≥ 98.55%
   - FPR: target ≤ 0.50%
   - Fraud caught: target ~1,543 / 1,643
   - False alarms: target ~40 / 8,000
7. If metrics fall short — trigger hyperparameter re-tuning loop (allocated buffer: Day 5 afternoon)
8. Export model to TensorFlow SavedModel format for TensorFlow Serving: `models/serving/lstm_v1/`
9. Write `models/MODEL_CARD.md` — model version, training data, performance metrics, known bias patterns
10. Commit all; Maria updates project status report

**Deliverables:**
- `03_evaluation.ipynb`
- `results/final_metrics.json`
- `results/figures/confusion_matrix.png`
- `models/serving/lstm_v1/` (TF Serving format)
- `models/MODEL_CARD.md`

**Acceptance:** Metrics meet targets; confusion matrix matches Figure 12 in report; MODEL_CARD.md reviewed by Kevin

---

### Day 6 — Docker Containerisation & TensorFlow Serving Setup
**Owner:** Sourav, Kevin | **Phase:** Infrastructure

**Objectives:**
- Containerise the LSTM inference API so it can be called by the SIEM correlation engine
- Validate end-to-end inference latency < 1 second

**Tasks:**
1. Write `Dockerfile.serving` based on `tensorflow/serving` base image
2. Mount `models/serving/lstm_v1/` into the container
3. Expose REST endpoint: `POST /v1/models/lstm:predict` — accepts JSON transaction sequence, returns anomaly probability
4. Write `docker-compose.yml` — orchestrates: `lstm-serving`, `elasticsearch`, `kibana`, `logstash`, `feature-engineering-service`
5. Write `src/inference_client.py` — thin Python wrapper around the TF Serving REST API
6. Run latency benchmark: 100 sequential inference calls — must average < 200 ms per call
7. Write integration smoke test: `tests/test_inference_api.py` — sends a known fraud pattern and a known clean pattern, asserts correct outputs
8. Push Docker images to GitHub Container Registry
9. Kevin: prototype the SIEM integration point using a **fake scoring signal** (constant 0.74 anomaly score) — validates SIEM side before real LSTM is wired in (RM-05 mitigation)

**Deliverables:**
- `Dockerfile.serving`
- `docker-compose.yml`
- `src/inference_client.py`
- `tests/test_inference_api.py`
- Latency benchmark results in `results/latency_benchmark.json`

**Acceptance:** Smoke tests pass; latency < 200 ms p99; fake signal flows into SIEM without error

---

### Day 7 — Elastic SIEM Setup & Rule-Based Correlation Engine
**Owner:** Kevin (lead), Sourav | **Phase:** SIEM Integration

**Objectives:**
- Spin up self-hosted Elastic SIEM (Elasticsearch + Kibana + Beats + Logstash)
- Implement the 4 discrete threshold detection rules

**Tasks:**
1. Deploy Elastic stack via `docker-compose.yml` (Elasticsearch 8.x, Kibana, Logstash, Filebeat)
2. Configure Logstash pipeline `logstash/pipelines/transaction_ingest.conf`:
   - Input: simulated banking channel logs (JSON)
   - Filter: normalise fields to ECS (Elastic Common Schema)
   - Output: Elasticsearch index `meridian-transactions-*`
3. Write `src/siem/rule_engine.py` — `ElasticSIEMCorrelator` class with 4 rules:
   - **Rule 1:** `amount > 10000` → HIGH risk flag
   - **Rule 2:** Geo-velocity jump > 500 km/h between consecutive transactions → HIGH risk flag
   - **Rule 3:** Transaction outside business hours (before 08:00 or after 22:00 AEST) → MEDIUM risk flag
   - **Rule 4:** Merchant on known watchlist (`watchlist/merchants.json`) → HIGH risk flag
4. Each rule returns: `{rule_id, triggered: bool, severity: str, evidence: dict}`
5. Configure Kibana detection rules to mirror the above in the UI
6. Set up Kibana dashboards: Alert Feed, Transaction Timeline
7. Run mock transaction data through rule engine — verify all 4 rules trigger and suppress correctly
8. Commit `src/siem/rule_engine.py` and Kibana export `kibana/dashboards/`
9. Stand-up: Kevin demos SIEM ingestion to team

**Deliverables:**
- Elastic SIEM running via docker-compose
- `src/siem/rule_engine.py`
- `logstash/pipelines/transaction_ingest.conf`
- `kibana/dashboards/` (exported JSON)
- `watchlist/merchants.json`

**Acceptance:** All 4 rules trigger on seeded fraud data; clean data passes without alert; Kibana UI accessible at `localhost:5601`

---

## Week 2 — SIEM-LSTM Integration, Dashboard, Testing & Handover

---

### Day 8 — Hybrid Threat Scoring Engine (SIEM + LSTM Fusion)
**Owner:** Kevin (lead), Sourav | **Phase:** SIEM Integration

**Objectives:**
- Build the unified correlation wrapper that blends SIEM rule scores and LSTM anomaly probability into a single threat metric
- Trigger automated containment when the combined score exceeds 70%

**Tasks:**
1. Write `src/siem/hybrid_scorer.py` — `HybridThreatScorer` class:
   ```
   threat_score = (lstm_anomaly_score × 0.6) + (siem_rule_score × 0.4)
   ```
   - `siem_rule_score`: normalised 0–1 based on rules triggered (0=none, 0.33=1 rule, 0.67=2 rules, 1.0=3+ rules)
   - `lstm_anomaly_score`: raw sigmoid output from LSTM inference API
2. If `threat_score ≥ 0.70`: automatically trigger `PlaybookEngine.fire()`
3. Write `src/siem/playbook_engine.py` — `PlaybookEngine` class:
   - Generates incident response payload dict: `{incident_id, customer_id, action: "LOCK_ACCOUNT", timestamp, evidence, severity}`
   - Writes payload to Elasticsearch index `meridian-incidents-*`
   - Sends analyst notification (mock email/Teams webhook)
4. Wire `HybridThreatScorer` into the Logstash pipeline — every ingested event now gets a `threat_score` field
5. End-to-end test with CUST-18656 scenario (Darwin, NT — 6 online purchases at electronics/restaurant merchants):
   - All 4 SIEM rules should PASS (no individual rule fires)
   - LSTM should return anomaly score ~0.74
   - Combined threat score should exceed 0.70 → playbook fires
6. Log test evidence to `results/e2e_test_cust18656.json`
7. Commit and open PR — Sourav reviews

**Deliverables:**
- `src/siem/hybrid_scorer.py`
- `src/siem/playbook_engine.py`
- `results/e2e_test_cust18656.json`

**Acceptance:** CUST-18656 scenario: SIEM passes all rules, LSTM flags at 74%, playbook fires, incident record created in Elasticsearch

---

### Day 9 — RBAC, Security Controls & Compliance Mapping
**Owner:** Kevin (lead), Maria | **Phase:** Compliance & Security

**Objectives:**
- Implement Role-Based Access Control for all 6 user groups
- Begin compliance control mapping (PCI DSS v4.0, APRA CPS 234, Australian Privacy Act 1988)

**Tasks:**
1. Configure Elasticsearch/Kibana RBAC — create roles:
   - `security_analyst`: read alerts, create/update/close incidents
   - `senior_security_engineer`: above + write detection rules, edit playbooks
   - `ml_operations`: read + write model artifacts and retraining jobs
   - `compliance_officer`: read-only audit logs and compliance indices
   - `system_administrator`: full admin
   - `read_only_auditor`: read-only audit logs (external)
2. Test RBAC enforcement: attempt rule edit as `security_analyst` role → must be denied and logged (AT-9)
3. Enable TLS 1.3 on all Elasticsearch HTTP/transport connections
4. Enable AES-256 encryption at rest on all Elasticsearch indices
5. Configure API key management in Kibana Secrets Manager — no credentials in source code
6. Set Kibana session timeout: 15 minutes
7. Write `compliance/control_mapping.md`:
   - Map each APRA CPS 234 paragraph to system control
   - Map each PCI DSS v4.0 requirement to system control
   - Map Privacy Act 1988 APP principles to data handling controls
8. Maria: update requirements traceability matrix linking US-01–US-17 to test cases AT-1–AT-10
9. Phase-end compliance review with Compliance Officer checkpoint (simulated)

**Deliverables:**
- RBAC roles configured and tested
- `compliance/control_mapping.md`
- `docs/requirements_traceability_matrix.md`
- TLS + AES-256 confirmed active

**Acceptance:** RBAC denial test passes and is logged; compliance mapping covers all three frameworks; traceability matrix 100% coverage of Must Have stories

---

### Day 10 — Analyst Dashboard — Layout, Dark Theme & Live Data Wiring
**Owner:** Kevin (lead), Maria | **Phase:** UI/UX

**Objectives:**
- Build the Meridian SENTINEL v3.2 SOC dashboard as a React/Tailwind single-page application
- Wire mock data for the CUST-18656 investigation scenario

**Tasks:**
1. Bootstrap React app: `npx create-react-app meridian-dashboard --template typescript`
2. Install: `tailwindcss`, `lucide-react`, `recharts`, `axios`
3. Implement dark theme layout with 4 panels:
   - **Top Bar:** Real-time KPIs — Transactions Today (184,299), LSTM Detection Rate (98.55%), FPR (0.50%), Active Alerts count, Analyst session info
   - **Left Panel — Live Transaction Feed:** Scrolling list of incoming transactions with SIEM PASS/FAIL badge and LSTM risk bar
   - **Centre Panel — Detection Comparison (SIEM vs LSTM):** Side-by-side view; left = SIEM rule checklist (4 rules with PASS/FLAG); right = LSTM behavioural anomaly evidence list; Hybrid threat score badge at bottom
   - **Right Panel — Analyst Alert Queue:** Alert card with severity badge, SLA countdown timer (04:08), "Confirm Threat" and "Investigate" action buttons
4. Inject CUST-18656 mock JSON data:
   - 6 transactions: $256.74, $71.28, $61.59, $69.46, $59.53, $146.60
   - Channels: Card, Online — Darwin NT — MCC 5732 (electronics) and MCC 5812 (restaurants)
   - SIEM: all 4 rules PASS; LSTM: 74% suspicious; Hybrid: FLAGGED
5. Add `Compliance & Audit Trail` panel (bottom right) with PCI DSS, APRA CPS 234, Privacy Act compliance badge indicators
6. Add `Hybrid Performance` mini chart (last 30 events): recharts LineChart of LSTM rolling signal vs detection mix
7. Deploy to Vercel: `vercel --prod` — obtain live URL
8. Commit dashboard code to `frontend/` directory in repo

**Deliverables:**
- `frontend/` React app
- Live Vercel URL
- CUST-18656 scenario renders correctly

**Acceptance:** Dashboard loads at Vercel URL; all 4 panels visible; CUST-18656 data populates correctly; threat score shows "FLAGGED — 74% SUSPICIOUS"

---

### Day 11 — Accessibility Audit & Dashboard Refinement
**Owner:** Kevin, Maria | **Phase:** UI/UX

**Objectives:**
- Ensure dashboard meets WCAG 2.2 Level AA
- Connect dashboard to live Elasticsearch backend for real alert polling

**Tasks:**
1. Accessibility audit — check every interactive element:
   - All buttons: `aria-label`, `role`, `tabIndex`
   - Alert feed items: keyboard navigable with arrow keys
   - Colour contrast: all text ≥ 4.5:1 ratio (use WCAG Contrast Checker)
   - Screen reader: add `aria-live="polite"` regions for new alert arrivals
   - Focus ring: visible on all interactive elements
   - Skip-to-content link at top of page
2. Fix any contrast failures — dark theme palette must use: background `#0f172a`, text `#f1f5f9`, alert red `#ef4444` (checked at 7.2:1)
3. Connect dashboard to Elasticsearch REST API:
   - `GET /meridian-transactions-*/_search` → live transaction feed
   - `GET /meridian-incidents-*/_search` → active alert queue
   - Poll every 5 seconds with `setInterval`
4. Add "Confirm Threat" button action → `POST /meridian-incidents/{id}` with `{action: "CONFIRMED", analyst_id, timestamp}` → updates audit log
5. Add "Investigate" button → opens detailed incident drawer
6. Session timeout warning modal at 14:00 → auto logout at 15:00
7. Re-deploy to Vercel after accessibility fixes
8. Run Lighthouse accessibility audit — target score ≥ 90
9. Document accessibility features in `docs/accessibility-audit.md`

**Deliverables:**
- Accessibility-compliant dashboard (Lighthouse ≥ 90)
- `docs/accessibility-audit.md`
- Live alert polling from Elasticsearch

**Acceptance:** All WCAG 2.2 AA criteria met; "Confirm Threat" action writes to Elasticsearch audit log; keyboard navigation reaches all controls

---

### Day 12 — End-to-End Integration Testing (AT-1 through AT-10)
**Owner:** All three | **Phase:** Testing & Evaluation

**Objectives:**
- Run the full acceptance test suite
- Produce a passing verification checklist

**Tasks:**
1. Write `tests/test_acceptance.py` — 10 integration test cases:
   - **AT-1:** Feed PaySim log → appears in Elasticsearch within 2 seconds
   - **AT-2:** Known fraud pattern → LSTM anomaly score > 0.70 threshold
   - **AT-3:** Known clean pattern → LSTM anomaly score < 0.30
   - **AT-4:** Full threat scenario → SIEM alert fires within 1 second
   - **AT-5:** High-severity alert → playbook fires; containment action logged; analyst notified
   - **AT-6:** Analyst triages and closes alert → status change recorded in audit log
   - **AT-7:** Export compliance report → includes PCI DSS and APRA CPS 234 control evidence
   - **AT-8:** Dashboard keyboard navigation → all functions reachable without mouse
   - **AT-9:** `security_analyst` role attempts rule edit → access denied and logged
   - **AT-10:** Retraining pipeline runs → new model version promoted with validation report
2. Execute full test suite: `pytest tests/test_acceptance.py -v --tb=short`
3. Record results in `results/acceptance_test_report.md` — expected output: all 10 PASS
4. For any failures: log as Jira bug, apply fix, re-run before Day 13
5. Run performance benchmarks:
   - Ingestion latency: < 2 seconds (AT-1)
   - Alert latency: < 1 second (AT-4)
   - LSTM inference: < 200 ms p99
6. Maria: update project status report — metrics collection plan completed

**Deliverables:**
- `tests/test_acceptance.py`
- `results/acceptance_test_report.md` — all 10 AT PASS

**Acceptance:** All 10 acceptance test cases pass; no P1 bugs open

---

### Day 13 — Security Review, Penetration Testing & Bug Fixes
**Owner:** Kevin (lead) | **Phase:** Compliance & Security

**Objectives:**
- Conduct security review of the complete prototype
- Close all open bugs from Day 12 testing

**Tasks:**
1. Security review checklist:
   - Confirm no API keys, passwords or cloud credentials in source code (git-secrets scan)
   - Confirm TLS 1.3 active on all endpoints
   - Confirm AES-256 encryption at rest
   - Confirm RBAC enforced for all 6 roles
   - Confirm PII obfuscation at ingestion (no raw names in Elasticsearch)
   - Confirm session timeout at 15 minutes
   - Confirm audit trail immutability (no delete permissions on `meridian-audit-*` index)
2. Run OWASP ZAP scan against the Kibana dashboard and React frontend
3. Document findings in `security/security_review_report.md`
4. Remediate any HIGH findings before handover
5. Fix all P1 and P2 bugs from Day 12 test run
6. Re-run affected acceptance tests after bug fixes
7. Kevin: write `docs/responsible_disclosure_policy.md`
8. Maria: prepare CISO sign-off checklist (all Must Have features, all ATs passing, all docs complete)
9. Merge `dev` → `main` via GitHub pull request — requires 2 approvals (Sourav + Maria)
10. Tag release: `git tag v1.0.0-prototype`

**Deliverables:**
- `security/security_review_report.md`
- `docs/responsible_disclosure_policy.md`
- `v1.0.0-prototype` tag on `main`
- Zero open P1 bugs

**Acceptance:** No HIGH security findings unresolved; `main` branch is clean; all acceptance tests green on `main`

---

### Day 14 — Documentation, Training & Final Handover
**Owner:** All three | **Phase:** Handover & Closure

**Objectives:**
- Deliver complete institutional-grade documentation
- Conduct training sessions for Meridian IT Security Team
- Obtain CISO and Compliance Officer sign-off

**Tasks:**
1. Finalise `README.md` — institutional-grade handbook:
   - Project abstract
   - High-level architecture overview with diagram references
   - Developer deployment commands (Docker, Colab, Vercel)
   - Compliance reference matrix (APRA CPS 234, PCI DSS v4.0, Privacy Act 1988)
   - Model performance outcomes table
   - Known limitations section
2. Write `docs/analyst-guide.md` — how to triage alerts, use action buttons, interpret LSTM vs SIEM comparison
3. Write `docs/incident-response-runbook.md` — step-by-step incident response procedures
4. Write `docs/model-retraining-guide.md` — how to trigger retraining, validate new model version, promote to serving
5. Write `docs/handover-checklist.md` — final sign-off checklist for CISO
6. Training Session 1 (60 min): Security Analysts — dashboard navigation, alert triage, incident workflow
7. Training Session 2 (60 min): IT Security Team — SIEM administration, playbook management, RBAC
8. Collect feedback forms from training attendees
9. Maria: deliver final project status report to CISO and Compliance Officer
10. Obtain CISO sign-off on `docs/handover-checklist.md`
11. Archive all Colab notebooks to GitHub `notebooks/` directory
12. Final team retrospective — document lessons learned in `docs/retrospective.md`

**Deliverables:**
- `README.md` (final)
- `docs/analyst-guide.md`
- `docs/incident-response-runbook.md`
- `docs/model-retraining-guide.md`
- `docs/handover-checklist.md` (signed)
- `docs/retrospective.md`
- Training sessions delivered
- CISO sign-off obtained

**Acceptance:** All deliverables from Table 2 of the project report handed over; CISO signs handover checklist; Meridian IT Security Team confirmed ready to operate the system

---

## Milestone Summary

| Milestone | Day | Owner | Evidence |
|-----------|-----|-------|----------|
| Repo & CI live | 1 | All | CI badge green |
| Feature pipeline complete | 2 | Sourav | `.npy` arrays exported |
| LSTM model trained | 4 | Sourav | `lstm_final.pt` saved |
| Metrics targets hit | 5 | Sourav | `final_metrics.json` ≥ 98.55% |
| SIEM ingestion live | 7 | Kevin | Kibana shows events |
| Hybrid scoring engine live | 8 | Kevin | CUST-18656 playbook fires |
| Dashboard deployed | 10 | Kevin/Maria | Vercel URL live |
| All ATs passing | 12 | All | `acceptance_test_report.md` |
| Security review clean | 13 | Kevin | Zero HIGH findings |
| Handover complete | 14 | All | CISO sign-off |

---

## Daily Rituals

- **08:30 daily stand-up** (15 min): What did I do yesterday? What am I doing today? Any blockers?
- **Friday weekly review** (60 min): Planned vs actual progress, risk register update, metrics review
- **Phase-end compliance checkpoint**: Kevin + Maria review control mapping before moving to next phase
- **Bug handling**: Copy full error trace → paste to AI assistant → get corrected code block → test → commit
