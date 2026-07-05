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

*(Empty — Day 14 complete — build finished)*

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
  - [x] Full training (35 epochs, pos_weight=1.0 + WeightedRandomSampler) → `results/training_history.json`, `results/figures/training_curves.png`
  - [x] Evaluated on test set at threshold=0.92 → accuracy 98.86%, recall 63.8%, FPR 1.10% (sweep-selected threshold)
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

- [x] **Acceptance Testing — Day 12**
  - [x] `tests/test_acceptance.py` — 10 ATs (AT-1 through AT-10) in one file
  - [x] Unit tier (32 tests, no Docker): AT-2, AT-3, AT-4, AT-5, AT-7, AT-8, AT-10 — **32/32 PASS**
  - [x] Integration tier (3 tests): AT-1 (Logstash latency), AT-6 (analyst audit), AT-9 (RBAC denial) — require `docker compose up`
  - [x] `Dockerfile.dev` — added `torch==2.3.0+cpu` so AT-2/AT-3/AT-10 run in dev container
  - [x] `results/acceptance_test_report.md` — full AT-1–AT-10 evidence report
  - [x] `docs/requirements_traceability_matrix.md` — updated with Day 12 pass/fail status for all 10 ATs
  - [x] Run command: `pytest tests/test_acceptance.py -v -m "not integration"` → 32 passed in 2.56s

- [x] **Live Integration Tests + Security Review — Day 13**
  - [x] Brought up full Docker stack (ES, Kibana, Logstash, lstm-serving) and fixed 7 blocking issues:
    Logstash 8.11 DSL parse error, xpack monitoring 401s, Kibana service-account token requirement,
    `LOGSTASH_HOST` Docker networking, `json_lines` codec format, RBAC `auto_configure` denial, wrong test usernames
  - [x] `tests/test_acceptance.py -v` (full suite, no marker filter) → **35/35 PASS in 3.43s**
  - [x] `results/acceptance_test_report.md` — updated AT-1/AT-6/AT-9 from Integration to PASS with live evidence
  - [x] `docs/requirements_traceability_matrix.md` — updated to 35/35 PASS
  - [x] `results/security_review.md` — credential/secret scan (no leaked secrets, `.env` correctly gitignored)
  - [x] `results/zap_report.html` — OWASP ZAP baseline scan vs Vercel deployment: **0 FAIL, 6 WARN (low/info), 60 PASS**
  - [x] `feature/day13-security-merge` branch created for this work
  - [x] Merged to `main`, tagged `v1.0.0-prototype`, pushed to origin

- [x] **Documentation — Day 14**
  - [x] `README.md` — updated to reflect Days 9–14; adds dashboard quickstart, RBAC bootstrap step, release table
  - [x] `docs/analyst-guide.md` — SOC analyst triage workflow, panel descriptions, CUST-18656 walkthrough, keyboard navigation notes
  - [x] `docs/runbook.md` — startup, RBAC bootstrap, health checks, retraining procedure, incident response, common failures, release procedure
  - [x] `docs/retrospective.md` — 14-day retrospective: delivery summary, what went well, what went poorly, production hardening recommendations
  - [x] `onboarding.md` — day-by-day status table brought current; doc reading order updated to include analyst guide and runbook

- [x] **US-07:** React SOC Dashboard — Day 11 (accessibility + live polling)
  - [x] `useElasticPolling.ts` — polls ES every 5s in dev via Vite proxy; graceful mock fallback on Vercel
  - [x] `useIdleTimer.ts` — 14-min warn / 15-min logout; monitors 5 activity event types
  - [x] `useA11yAnnouncer.ts` — visually-hidden `aria-live="polite"` region for screen reader announcements
  - [x] `SessionWarningModal.tsx` — 60-second countdown, focus trap, Escape dismisses
  - [x] `InvestigateDrawer.tsx` — slide-in right drawer, transaction timeline table, hybrid score breakdown, focus trap
  - [x] `Toast.tsx` — 4-second auto-dismiss, `role="alert"`, `aria-live="assertive"`
  - [x] LIVE/DEMO indicator in TopBar (green Wifi = ES connected, grey WifiOff = mock)
  - [x] Confirm Threat button — POST to ES audit index; optimistic UI update + toast on success or fallback
  - [x] Investigate button — opens InvestigateDrawer
  - [x] Vite proxy: `/api/*` → `localhost:9200/*` in dev
  - [x] `index.html` — skip-to-content link, `<title>` updated
  - [x] TransactionFeed — `role="list/listitem"`, `tabIndex={0}`, LSTM bar has `role="progressbar"`
  - [x] `docs/accessibility-audit.md` — full WCAG 2.2 AA checklist, contrast ratios, session security
  - [x] Build passes: zero TypeScript errors
  - [x] Re-deployed to Vercel

- [x] **US-07:** React SOC Dashboard — Day 10 (mock data phase)
  - [x] Vite + React + TypeScript scaffolded in `frontend/`
  - [x] Tailwind CSS v4 configured (`@tailwindcss/vite` plugin)
  - [x] `frontend/src/types/index.ts` — TypeScript interfaces (Transaction, SIEMResult, Incident, KPIStats, HistoryEvent)
  - [x] `frontend/src/data/mockData.ts` — KPI stats, CUST-18656 6-transaction scenario, SIEM result, incident, 30-event chart history
  - [x] `TopBar.tsx` — KPIs (transactions, detection rate, FPR, active alerts), analyst name, live clock
  - [x] `TransactionFeed.tsx` — 16 transactions (10 clean + 6 CUST-18656), LSTM bar, SIEM PASS badge, amber highlight on active investigation
  - [x] `DetectionPanel.tsx` — SIEM rule checklist (4 rules, all PASS), LSTM anomaly bar at 74%, LSTM_ALONE verdict banner
  - [x] `AlertQueue.tsx` — CUST-18656 alert card, SLA countdown timer (live setInterval), Confirm Threat + Investigate buttons
  - [x] `HybridChart.tsx` — Recharts LineChart, LSTM (blue) + Hybrid (amber) lines, 0.70 trigger reference line, CUST-18656 annotation dot
  - [x] `ComplianceBadges.tsx` — APRA CPS 234, PCI DSS v4.0, Privacy Act 1988 status badges
  - [x] `vercel.json` — SPA rewrite rule for Vercel deployment
  - [x] Build passes: `npm run build` — zero TypeScript errors
  - [x] Acceptance criteria: DetectionPanel shows FLAGGED — LSTM ALONE · 74% SUSPICIOUS ✅

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
