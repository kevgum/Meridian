# Requirements Traceability Matrix — Meridian Sentinel

> **Document version:** 1.0  
> **Project:** Meridian Sentinel — Hybrid Real-Time Fraud Detection Prototype  
> **Course:** ITW601  
> **Date:** 2026-06-30  
>
> This matrix traces each Must Have user story (US) to the acceptance test (AT)
> that verifies it, the day it was implemented, and the source files that provide
> audit evidence.

---

## Coverage Summary

| Framework item | Count | AT coverage |
|----------------|-------|------------|
| Must Have user stories (US-01–US-11) | 11 | 100% |
| Acceptance tests (AT-1–AT-10) | 10 | 100% |
| Should Have stories mapped | 3 | Partial |

---

## Must Have User Stories → Acceptance Tests

| US | User Story | Priority | AT Coverage | Day Implemented | Status | Evidence Files |
|----|-----------|----------|------------|----------------|--------|---------------|
| US-01 | Load and preprocess PaySim synthetic dataset into 12-feature sequences of length 5 | Must Have | AT-2, AT-3 (indirectly) | Day 2 | ✅ Done | [`src/pipeline/feature_engineering.py`](../src/pipeline/feature_engineering.py) |
| US-02 | Ingest banking channel logs into Elasticsearch within 2 seconds via Logstash ECS pipeline | Must Have | **AT-1** | Day 7 | ✅ Done | [`logstash/pipelines/transaction_ingest.conf`](../logstash/pipelines/transaction_ingest.conf) |
| US-03 | Train LSTM model to achieve ≥ 98.55% detection accuracy and ≤ 0.50% FPR on held-out test set | Must Have | **AT-2**, **AT-3** | Days 3–5 | ✅ Done | [`models/MODEL_CARD.md`](../models/MODEL_CARD.md), [`results/final_metrics.json`](../results/final_metrics.json) |
| US-04 | Serve LSTM model via REST API (POST /v1/models/lstm:predict) with p99 latency < 200 ms | Must Have | **AT-2**, **AT-3** | Day 6 | ✅ Done | [`src/serving/app.py`](../src/serving/app.py), [`tests/test_inference_api.py`](../tests/test_inference_api.py), [`results/latency_benchmark.json`](../results/latency_benchmark.json) |
| US-05 | Evaluate 4 SIEM detection rules (high-value, geo-velocity, off-hours, watchlist) and return normalised score | Must Have | **AT-4** | Day 7 | ✅ Done | [`src/siem/rule_engine.py`](../src/siem/rule_engine.py), [`tests/test_siem_rules.py`](../tests/test_siem_rules.py) |
| US-06 | Compute hybrid threat score (lstm × 0.60 + siem × 0.40); fire playbook when score ≥ 0.70 | Must Have | **AT-4**, **AT-5** | Day 8 | ✅ Done | [`src/siem/hybrid_scorer.py`](../src/siem/hybrid_scorer.py), [`tests/test_hybrid_scorer.py`](../tests/test_hybrid_scorer.py) |
| US-07 | Create incident record, lock account, and notify analyst when playbook fires | Must Have | **AT-5** | Day 8 | ✅ Done | [`src/siem/playbook_engine.py`](../src/siem/playbook_engine.py), [`results/e2e_test_cust18656.json`](../results/e2e_test_cust18656.json) |
| US-08 | Analyst dashboard: display live alert feed, SIEM vs LSTM comparison, and action queue | Must Have | **AT-6**, **AT-8** | Days 10–11 | ⬜ Not started | `frontend/` (to be built) |
| US-09 | Analyst can confirm or close an alert; action is recorded in the immutable audit trail | Must Have | **AT-6** | Days 10–11 | ⬜ Not started | `frontend/` (to be built) |
| US-10 | Export compliance report covering PCI DSS v4.0, APRA CPS 234, and Privacy Act controls | Must Have | **AT-7** | Day 7 | ✅ Done | [`compliance/control_mapping.md`](../compliance/control_mapping.md) |
| US-11 | RBAC: enforce role boundaries so security_analyst cannot edit detection rules | Must Have | **AT-9** | Day 9 | ✅ Done | [`scripts/bootstrap_rbac.py`](../scripts/bootstrap_rbac.py), [`tests/test_rbac.py`](../tests/test_rbac.py) |

---

## Should Have User Stories

| US | User Story | Priority | AT Coverage | Day | Status |
|----|-----------|----------|------------|-----|--------|
| US-12 | Dashboard WCAG 2.2 Level AA accessibility (keyboard navigation, contrast, screen reader) | Should Have | **AT-8** | Day 11 | ⬜ Not started |
| US-13 | TLS 1.3 on all Elasticsearch HTTP/transport connections | Should Have | — | Day 9 | 🔄 Config provided; cert infrastructure deferred to production |
| US-14 | AES-256 encryption at rest for all Elasticsearch indices | Should Have | — | Day 9 | 🔄 Config documented; requires ES Platinum/Enterprise licence |

---

## Acceptance Test → User Story Reverse Mapping

| AT | Acceptance Test | US Coverage | Test File | Status |
|----|----------------|------------|-----------|--------|
| AT-1 | Banking channel log ingested into Elasticsearch within 2 seconds | US-02 | `tests/test_acceptance.py` (Day 12) | ⬜ Pending |
| AT-2 | Known fraud pattern → LSTM anomaly score > 0.70 | US-03, US-04 | [`tests/test_inference_api.py`](../tests/test_inference_api.py) | ✅ Covered |
| AT-3 | Known clean pattern → LSTM anomaly score < 0.30 | US-03, US-04 | [`tests/test_inference_api.py`](../tests/test_inference_api.py) | ✅ Covered |
| AT-4 | Full threat scenario → SIEM alert fires within 1 second | US-05, US-06 | [`tests/test_hybrid_scorer.py`](../tests/test_hybrid_scorer.py) | ✅ Covered (unit) |
| AT-5 | High-severity alert → playbook fires; account locked; analyst notified | US-07 | [`tests/test_hybrid_scorer.py`](../tests/test_hybrid_scorer.py) | ✅ Covered (unit) |
| AT-6 | Analyst closes alert → status recorded in audit log | US-08, US-09 | `tests/test_acceptance.py` (Day 12) | ⬜ Pending |
| AT-7 | Export compliance report → includes PCI DSS and APRA CPS 234 evidence | US-10 | [`compliance/control_mapping.md`](../compliance/control_mapping.md) | ✅ Covered (doc) |
| AT-8 | Dashboard keyboard navigation reaches all functions | US-08, US-12 | `tests/test_acceptance.py` (Day 12) | ⬜ Pending |
| AT-9 | security_analyst role attempts rule edit → access denied and logged | US-11 | [`tests/test_rbac.py`](../tests/test_rbac.py) | ✅ Covered (integration) |
| AT-10 | Retraining pipeline → new model version promoted with validation report | US-03 | `tests/test_acceptance.py` (Day 12) | ⬜ Pending |

---

## Test Coverage Gap Analysis

| AT | Gap | Resolution |
|----|-----|-----------|
| AT-1 | No test yet for sub-2-second Logstash ingestion latency | Day 12 acceptance test with timed ES index check |
| AT-6 | Analyst close action requires dashboard to be built | Days 10–11 dashboard + Day 12 acceptance test |
| AT-8 | Keyboard nav requires React component tree to exist | Day 11 accessibility audit + Day 12 test |
| AT-10 | Retraining pipeline not yet scripted | Day 13 — `scripts/retrain.py` + model promotion logic |

**5 of 10 ATs are already covered** by existing tests (AT-2, AT-3, AT-4, AT-5, AT-7, AT-9 = 6 tests with unit/integration/doc evidence).  
**4 ATs** depend on the Day 10–11 dashboard and the Day 12 formal acceptance test suite.

---

## Evidence Traceability by Compliance Framework

| Control | APRA CPS 234 | PCI DSS v4.0 | Privacy Act | Evidence |
|---------|-------------|-------------|------------|---------|
| PII hashing at ingestion | Para 17 | Req 3.5 | APP 6, APP 11 | `logstash/pipelines/transaction_ingest.conf` |
| RBAC — 6 roles enforced | Para 15–21 | Req 7.2 | — | `scripts/bootstrap_rbac.py`, `tests/test_rbac.py` |
| Immutable audit trail | Para 22 | Req 10.3 | APP 11 | `meridian-audit-*` ES index |
| Incident response playbook | Para 36–37 | Req 12.10 | — | `src/siem/playbook_engine.py` |
| Session timeout (15 min) | Para 21 | Req 8.2.8 | — | `docker-compose.yml` (Kibana env) |
| TLS 1.3 in transit | Para 17 | Req 4.2.1 | APP 11 | `scripts/generate_certs.sh` (config provided) |
| AES-256 at rest | Para 17 | Req 3.5 | APP 11 | Documented; requires ES Platinum licence |
| LSTM anomaly detection | Para 15 | Req 12.3 | — | `src/serving/app.py`, `tests/test_inference_api.py` |
| SIEM rule engine | Para 15 | Req 10.7 | — | `src/siem/rule_engine.py`, `tests/test_siem_rules.py` |
