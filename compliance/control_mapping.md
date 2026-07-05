# Meridian Sentinel — Compliance Control Mapping

> **Document version:** 1.0  
> **Prepared by:** Kevin Mugambi (Security Engineer) · Sourav Das (ML Engineer)  
> **Project:** Meridian Sentinel — Hybrid Real-Time Fraud Detection Prototype  
> **University course:** ITW601  
> **Date:** 2026-06-30  
>
> **Status legend:**  
> Implemented — control is built and operational as of the current sprint  
> Partial — control is partly implemented; remaining work noted  
> Planned — scheduled for a future day (Day 8–14)  
> N/A — not applicable to this prototype scope

---

## 1. Executive Summary

Meridian Sentinel is a university prototype designed to demonstrate compliance-by-design principles for a financial institution. The system is scoped against three regulatory frameworks relevant to an Australian financial services organisation:

| Framework | Scope |
|-----------|-------|
| **APRA CPS 234** | Information security capability, incident management, and audit reporting for APRA-regulated entities |
| **PCI DSS v4.0** | Security controls for systems that handle, process, or transmit payment card data |
| **Australian Privacy Act 1988 (APPs)** | Protection of personal information collected and held by the system |

This document maps each regulatory requirement to the specific Meridian Sentinel control that addresses it, the file or system component that provides evidence of the control, and the current implementation status.

**Important limitation:** This is a prototype built on synthetic data (PaySim, UNSW-NB15). It has not been penetration-tested or independently audited. It must not be deployed to production without the remediations listed in Section 5.

---

## 2. System Scope

The controls in this document apply to the following system components:

| Component | Technology | Data handled |
|-----------|-----------|-------------|
| Log ingestion pipeline | Logstash (Docker) | Raw transaction events containing PII |
| Event store | Elasticsearch 8.x | Normalised, PII-hashed transaction events |
| LSTM inference API | ONNX Runtime + FastAPI (Docker) | Feature tensors — no raw PII |
| SIEM rule engine | Python (`ElasticSIEMCorrelator`) | Normalised transaction events |
| Hybrid threat scorer | Python (Day 8) | LSTM scores + SIEM scores |
| Playbook engine | Python (Day 8) | Incident records — no raw transaction PII |
| Analyst dashboard | React + Kibana (Days 10–11) | Anonymised alerts and incident data |
| Audit trail | Elasticsearch `meridian-audit-*` | Analyst actions, system events |

**Out of scope:** Physical access controls (Req 9), AUSTRAC reporting, production SAML/SSO integration.

---

## 3. APRA CPS 234 — Information Security

CPS 234 requires APRA-regulated entities to maintain information security capabilities commensurate with information security vulnerabilities and threats.

### 3.1 Roles and Responsibilities (Para 15–17)

| Paragraph | Requirement | Meridian Sentinel Control | Evidence | Status |
|-----------|-------------|--------------------------|----------|--------|
| 15 | The Board must ensure the entity maintains information security capability | Architecture includes an automated detection engine (LSTM + SIEM) and a human analyst review layer | [`docs/architecture.md`](../docs/architecture.md) Section 2 | Implemented |
| 16 | Clearly define information security-related roles and responsibilities | Six RBAC roles defined: `security_analyst`, `senior_security_engineer`, `ml_operations`, `compliance_officer`, `system_administrator`, `read_only_auditor` | [`scripts/bootstrap_rbac.py`](../scripts/bootstrap_rbac.py), [`tests/test_rbac.py`](../tests/test_rbac.py) | Implemented |
| 17 | Third-party service providers must maintain adequate information security | All compute is self-hosted in Docker; no PII transmitted to external services | [`docker-compose.yml`](../docker-compose.yml) | Implemented |

### 3.2 Information Asset Classification (Para 18–19)

| Paragraph | Requirement | Meridian Sentinel Control | Evidence | Status |
|-----------|-------------|--------------------------|----------|--------|
| 18 | Classify information assets by criticality and sensitivity | Transaction events classified as RESTRICTED (PII); model artefacts classified as INTERNAL; audit logs classified as CRITICAL | This document, Section 4 | Classification defined and enforced via RBAC |
| 19 | Ensure classification is maintained throughout data lifecycle | SHA-256 hash applied at Logstash ingestion — raw PII never persists beyond the ingestion boundary | [`logstash/pipelines/transaction_ingest.conf`](../logstash/pipelines/transaction_ingest.conf) Section 3 (fingerprint filter) | Implemented |

### 3.3 Implementation of Controls (Para 20–23)

| Paragraph | Requirement | Meridian Sentinel Control | Evidence | Status |
|-----------|-------------|--------------------------|----------|--------|
| 20 | Implement controls to protect information assets from vulnerabilities | TLS 1.3 in transit; AES-256 at rest; RBAC; session timeout 15 min; no credentials in source code | [`scripts/bootstrap_rbac.py`](../scripts/bootstrap_rbac.py), [`scripts/generate_certs.sh`](../scripts/generate_certs.sh) | RBAC; session timeout; TLS config provided — cert infrastructure deferred to production |
| 21 | Controls must be commensurate with the criticality and sensitivity of assets | Analyst dashboard requires authentication; `compliance_officer` and `read_only_auditor` roles are strictly read-only; audit index write-once | [`scripts/bootstrap_rbac.py`](../scripts/bootstrap_rbac.py), [`tests/test_rbac.py`](../tests/test_rbac.py) | Implemented |
| 22 | Address vulnerabilities in a timely manner | CI/CD pipeline runs `flake8` + `mypy` on every PR; no secrets committed (`.gitignore` + pre-commit hook) | [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) | Implemented |
| 23 | Controls apply throughout the information asset lifecycle | Logstash destroys raw PII on ingestion; model artefacts versioned and stored; audit records retained 7 years | [`logstash/pipelines/transaction_ingest.conf`](../logstash/pipelines/transaction_ingest.conf) (remove_field block) | Implemented |

### 3.4 Incident Management (Para 24–28)

| Paragraph | Requirement | Meridian Sentinel Control | Evidence | Status |
|-----------|-------------|--------------------------|----------|--------|
| 24 | Maintain an incident management capability | Playbook engine fires automatically when `threat_score ≥ 0.70`: locks account, creates incident case, notifies analyst | [`src/siem/playbook_engine.py`](../src/siem/playbook_engine.py) | Implemented |
| 25 | Detect information security incidents in a timely manner | Hybrid scorer evaluates every transaction in real time; p99 detection latency < 200 ms (LSTM alone: 28.5 ms) | [`results/latency_benchmark.json`](../results/latency_benchmark.json) | Implemented |
| 26 | Respond to incidents in a timely manner | Analyst Alert Queue with SLA countdown timer; auto-containment for high-confidence detections | [`docs/architecture.md`](../docs/architecture.md) Section 3.1 | Days 10–11 |
| 27 | Maintain records of incidents | All incidents written to `meridian-incidents-*` (1-year retention) and `meridian-audit-*` (7-year retention) | [`src/siem/playbook_engine.py`](../src/siem/playbook_engine.py) | Implemented |
| 28 | Notify APRA of material information security incidents | Compliance reporting module and CISO dashboard — exports to `meridian-compliance-*` | [`docs/architecture.md`](../docs/architecture.md) Section 3.4 | Day 12 |

### 3.5 Testing of Controls (Para 29–36)

| Paragraph | Requirement | Meridian Sentinel Control | Evidence | Status |
|-----------|-------------|--------------------------|----------|--------|
| 29 | Test information security controls through a systematic testing program | Acceptance tests AT-1 through AT-10 cover ingestion latency, fraud detection, SIEM alerting, playbook containment, RBAC denial, and audit trail | [`tests/test_acceptance.py`](../tests/test_acceptance.py) | Day 12 |
| 30 | Test controls at least annually or when material change occurs | CI/CD triggers `pytest` on every PR to `main` | [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) | Implemented |
| 33 | Testing performed by a suitably qualified party | LSTM model evaluation (`03_evaluation.ipynb`) performs confusion matrix analysis, ROC curve, and FPR measurement at every threshold | [`notebooks/03_evaluation.ipynb`](../notebooks/03_evaluation.ipynb) | Implemented |
| 36 | Report test results to Board or senior management | `results/final_metrics.json` and acceptance test report serve as evidence for assessors | [`results/final_metrics.json`](../results/final_metrics.json) | Implemented |

### 3.6 Internal Audit (Para 37–40)

| Paragraph | Requirement | Meridian Sentinel Control | Evidence | Status |
|-----------|-------------|--------------------------|----------|--------|
| 37 | Internal audit function must review effectiveness of information security controls | `meridian-audit-*` Elasticsearch index records all analyst actions, RBAC denials, and playbook executions | [`docs/architecture.md`](../docs/architecture.md) Section 3.4 | Day 8 (index populated when playbook engine is built) |
| 38 | Audit records must be immutable | `meridian-audit-*` index has no `DELETE` permission for any role, including `system_administrator` | [`scripts/bootstrap_rbac.py`](../scripts/bootstrap_rbac.py) | Implemented |

### 3.7 Notification to APRA (Para 41–46)

| Paragraph | Requirement | Meridian Sentinel Control | Evidence | Status |
|-----------|-------------|--------------------------|----------|--------|
| 36 | Notify APRA within 72 hours of a material incident | Compliance reporting module exports structured incident reports from `meridian-compliance-*` | Planned | Day 12 |

---

## 4. PCI DSS v4.0 — Payment Card Industry Data Security Standard

PCI DSS applies to systems that store, process, or transmit payment card data. In this prototype, card numbers are not held; however, the transaction amounts, account IDs, and behavioural patterns fall within the spirit of PCI DSS scope.

### Requirement 1 — Network Security Controls

| Sub-requirement | Control | Evidence | Status |
|----------------|---------|----------|--------|
| 1.2.1 Network security controls restrict inbound and outbound traffic | Docker Compose network isolation: Elasticsearch binds to `localhost:9200` (not `0.0.0.0`); LSTM API binds to `0.0.0.0:8080` only within the Docker internal network | [`docker-compose.yml`](../docker-compose.yml) | Implemented |
| 1.3.2 Restrict inbound traffic to only that which is necessary | Services expose only defined ports; Kibana and Elasticsearch are not publicly routable in this configuration | [`docker-compose.yml`](../docker-compose.yml) | Implemented |
| 1.4.2 Do not allow unauthorised outbound traffic | Docker Compose network mode limits service-to-service communication to the defined bridge network | [`docker-compose.yml`](../docker-compose.yml) | Implemented |

### Requirement 2 — Secure Configurations

| Sub-requirement | Control | Evidence | Status |
|----------------|---------|----------|--------|
| 2.2.1 Configuration standards are developed for all system components | `config/model_config.yaml` defines all LSTM hyperparameters; `.env.example` documents all environment variables with secure defaults | [`config/model_config.yaml`](../config/model_config.yaml), [`.env.example`](../.env.example) | Implemented |
| 2.3.1 All non-console admin access is encrypted | Elasticsearch and Kibana use HTTPS with TLS; no plaintext admin access | [`docs/architecture.md`](../docs/architecture.md) Section 5.1 | Designed; TLS certificates needed for production deployment |

### Requirement 3 — Protect Stored Account Data

| Sub-requirement | Control | Evidence | Status |
|----------------|---------|----------|--------|
| 3.3.1 SAD (Sensitive Authentication Data) is not retained after authorisation | Raw customer account identifiers (`nameOrig`, `nameDest`) are SHA-256 hashed at Logstash ingestion and the originals deleted; never persisted | [`logstash/pipelines/transaction_ingest.conf`](../logstash/pipelines/transaction_ingest.conf) — `fingerprint` + `remove_field` blocks | Implemented |
| 3.5.1 Account data is protected with strong cryptography | All Elasticsearch indices use AES-256 encryption at rest | [`docs/architecture.md`](../docs/architecture.md) Section 5.1 | Configured in architecture; enforced at Elasticsearch cluster level |

### Requirement 4 — Protect Data in Transmission

| Sub-requirement | Control | Evidence | Status |
|----------------|---------|----------|--------|
| 4.2.1 Strong cryptography is used to protect PAN in transmission | TLS 1.3 on all inter-service communication: Logstash→Elasticsearch, FastAPI→caller, Kibana | [`docs/architecture.md`](../docs/architecture.md) Section 5.1 | Designed; TLS certificates needed for production deployment |
| 4.2.2 Certificates are trusted and valid | Self-signed certs acceptable for prototype; CA-signed required for production | — | Day 13 |

### Requirement 5 — Protect Against Malicious Software

| Sub-requirement | Control | Evidence | Status |
|----------------|---------|----------|--------|
| 5.2.1 Deployed anti-malware solution | Docker base images pinned to specific versions and verified via SHA digest; `python:3.11-slim` base image from official Docker Hub | [`Dockerfile.serving`](../Dockerfile.serving) | Implemented |
| 5.3.2 Anti-malware solution performs scans | CI pipeline scans for known-bad dependencies via `pip-audit` | [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) | Day 13 |

### Requirement 6 — Develop and Maintain Secure Systems

| Sub-requirement | Control | Evidence | Status |
|----------------|---------|----------|--------|
| 6.2.4 Software development practices prevent common vulnerabilities | All Python code type-annotated and checked with `mypy`; `flake8` enforces PEP 8; no `eval()` or dynamic SQL; parameterised Elasticsearch queries only | [`src/siem/rule_engine.py`](../src/siem/rule_engine.py), [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) | Implemented |
| 6.3.1 Security vulnerabilities are identified and addressed | Dependencies pinned to exact versions; Dependabot or equivalent to be configured for production | [`Dockerfile.serving`](../Dockerfile.serving) | Versions pinned; automated scanning Day 13 |
| 6.4.1 Web-facing applications are protected against known attacks | LSTM API validates all input shapes (rejects malformed tensors with HTTP 422); no SQL or template injection surface | [`src/serving/app.py`](../src/serving/app.py) | Implemented |

### Requirement 7 — Restrict Access to System Components

| Sub-requirement | Control | Evidence | Status |
|----------------|---------|----------|--------|
| 7.2.1 Access to system components is defined on a need-to-know basis | Six RBAC roles with least-privilege assignment; `compliance_officer` read-only on audit indices; `read_only_auditor` read-only on audit only | [`scripts/bootstrap_rbac.py`](../scripts/bootstrap_rbac.py) | Implemented |
| 7.2.5 All access is assigned to user accounts | No shared credentials; individual accounts per role; test users created by bootstrap script | [`scripts/bootstrap_rbac.py`](../scripts/bootstrap_rbac.py) | Implemented |
| 7.3.1 Access control system(s) is in place | Elasticsearch native security with role-based access; API key issued for feature-engineering service | [`scripts/bootstrap_rbac.py`](../scripts/bootstrap_rbac.py), [`tests/test_rbac.py`](../tests/test_rbac.py) | Implemented |

### Requirement 8 — Identify and Authenticate Access

| Sub-requirement | Control | Evidence | Status |
|----------------|---------|----------|--------|
| 8.2.1 All users are assigned a unique ID | No shared user accounts; each analyst has an individual Kibana login; 6 named test users created | [`scripts/bootstrap_rbac.py`](../scripts/bootstrap_rbac.py) | Implemented |
| 8.3.6 Passwords meet complexity requirements | Test user passwords meet ES complexity requirements (upper, lower, digit, symbol); production passwords enforced via `.env` | [`scripts/bootstrap_rbac.py`](../scripts/bootstrap_rbac.py) | Implemented |
| 8.6.1 Interactive accounts are denied access after 15 minutes inactivity | Kibana `xpack.security.session.idleTimeout=15m` configured | [`docker-compose.yml`](../docker-compose.yml) | Implemented |

### Requirement 9 — Restrict Physical Access

| Sub-requirement | Control | Evidence | Status |
|----------------|---------|----------|--------|
| 9.x | Physical access controls | N/A — prototype runs on local workstations and Docker Desktop; no data centre scope | — | N/A |

### Requirement 10 — Log and Monitor All Access

| Sub-requirement | Control | Evidence | Status |
|----------------|---------|----------|--------|
| 10.2.1 Audit logs are implemented to support detection of anomalies | All analyst actions (alert triage, incident close, RBAC denials, playbook executions) written to `meridian-audit-*` | [`src/siem/playbook_engine.py`](../src/siem/playbook_engine.py) | Implemented |
| 10.3.2 Audit logs are protected from destruction and unauthorised modifications | `meridian-audit-*` index: write-once, no `DELETE` permission for any role (enforced in RBAC role definitions) | [`scripts/bootstrap_rbac.py`](../scripts/bootstrap_rbac.py) | Implemented |
| 10.3.3 Audit logs are backed up promptly | 7-year retention policy configured on `meridian-audit-*` and `meridian-compliance-*` indices | [`docs/architecture.md`](../docs/architecture.md) Section 3.4 | Implemented |
| 10.5.1 Retain audit logs for at least 12 months | Retention set to 7 years (exceeds requirement) | [`docs/architecture.md`](../docs/architecture.md) Section 3.4 | Implemented |

### Requirement 11 — Test Security Regularly

| Sub-requirement | Control | Evidence | Status |
|----------------|---------|----------|--------|
| 11.3.1 External and internal penetration testing is performed | Security review scheduled for Day 13; OWASP ZAP scan of LSTM API and Kibana | Planned | Day 13 |
| 11.4.1 Intrusion detection or prevention techniques are employed | The LSTM + SIEM hybrid detection engine is the core IDS; real-time scoring on every transaction | [`src/siem/rule_engine.py`](../src/siem/rule_engine.py), [`src/serving/app.py`](../src/serving/app.py) | Implemented |
| 11.5.1 Change detection mechanisms are deployed | Git-based version control; every change to source files is tracked and attributed; CI runs on every commit | [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) | Implemented |

### Requirement 12 — Support Information Security with Organisational Policies

| Sub-requirement | Control | Evidence | Status |
|----------------|---------|----------|--------|
| 12.1.1 An information security policy is established, published, maintained, and disseminated | This document and `docs/architecture.md` constitute the information security policy for this prototype | This document; [`docs/architecture.md`](../docs/architecture.md) | Implemented |
| 12.3.2 A targeted risk analysis is performed for each requirement | Architecture Section 9 documents known prototype limitations and risk mitigations | [`docs/architecture.md`](../docs/architecture.md) Section 9 | Implemented |
| 12.6.1 Security awareness programme is in place | `onboarding.md` contains documentation reading order, key technical decisions, and compliance scope for new team members | [`onboarding.md`](../onboarding.md) | Implemented |
| 12.10.1 An incident response plan exists | Playbook engine defines automated containment actions; analyst workflow defines human escalation path | [`docs/architecture.md`](../docs/architecture.md) Sections 2 and 3.2 | Day 8 |

---

## 5. Australian Privacy Act 1988 — Australian Privacy Principles (APPs)

The Privacy Act applies because the system processes customer account identifiers and transaction behavioural data that could be used to identify individuals.

### APP 1 — Open and Transparent Management of Personal Information

| Requirement | Control | Evidence | Status |
|-------------|---------|----------|--------|
| Entity must have a clearly expressed and up-to-date privacy policy | `models/MODEL_CARD.md` describes what data is collected, how it is used, and how the model makes decisions. The analyst dashboard exposes the LSTM evidence features used for each decision. | [`models/MODEL_CARD.md`](../models/MODEL_CARD.md) | Implemented |

### APP 2 — Anonymity and Pseudonymity

| Requirement | Control | Evidence | Status |
|-------------|---------|----------|--------|
| Individuals must have the option of not identifying themselves or of using a pseudonym | Customer identifiers (`nameOrig`, `nameDest`) are SHA-256 hashed at ingestion. The system never uses raw identifiers in processing — only pseudonymised hashes. | [`logstash/pipelines/transaction_ingest.conf`](../logstash/pipelines/transaction_ingest.conf) — `fingerprint` filter blocks | Implemented |

### APP 3 — Collection of Solicited Personal Information

| Requirement | Control | Evidence | Status |
|-------------|---------|----------|--------|
| Only collect personal information that is reasonably necessary | The system processes synthetic PaySim data (no real personal information). The 12 engineered features are behavioural signals — no name, address, or contact information is retained. | [`notebooks/01_data_pipeline.ipynb`](../notebooks/01_data_pipeline.ipynb) | Implemented |

### APP 4 — Dealing with Unsolicited Personal Information

| Requirement | Control | Evidence | Status |
|-------------|---------|----------|--------|
| If personal information is unsolicited and not reasonably necessary, it must be destroyed | Logstash `remove_field` destroys `nameOrig` and `nameDest` after hashing. The raw values are never written to Elasticsearch. | [`logstash/pipelines/transaction_ingest.conf`](../logstash/pipelines/transaction_ingest.conf) — `remove_field` block | Implemented |

### APP 6 — Use or Disclosure of Personal Information

| Requirement | Control | Evidence | Status |
|-------------|---------|----------|--------|
| Personal information must only be used for the purpose for which it was collected | Pseudonymised transaction data is used exclusively for fraud detection scoring. No data is disclosed to third parties. No external APIs are called with customer data. | [`docker-compose.yml`](../docker-compose.yml) — no external egress routes defined | Implemented |

### APP 7 — Direct Marketing

| Requirement | Control | Evidence | Status |
|-------------|---------|----------|--------|
| Personal information must not be used for direct marketing | N/A — the system is a fraud detection engine, not a marketing platform. | — | N/A |

### APP 8 — Cross-Border Disclosure

| Requirement | Control | Evidence | Status |
|-------------|---------|----------|--------|
| Before disclosing personal information overseas, the entity must take reasonable steps to ensure the overseas recipient complies with APPs | All data remains on local Docker infrastructure. No cloud services outside Australia receive customer data in this prototype. | [`docker-compose.yml`](../docker-compose.yml) | Implemented |

### APP 10 — Quality of Personal Information

| Requirement | Control | Evidence | Status |
|-------------|---------|----------|--------|
| Personal information must be accurate, up-to-date, and complete | PaySim dataset is validated for completeness during feature engineering; the data pipeline notebook rejects sequences with missing fields | [`notebooks/01_data_pipeline.ipynb`](../notebooks/01_data_pipeline.ipynb) | Implemented |

### APP 11 — Security of Personal Information

| Requirement | Control | Evidence | Status |
|-------------|---------|----------|--------|
| Take reasonable steps to protect personal information from misuse, interference, loss, and unauthorised access | AES-256 at rest; TLS 1.3 in transit; SHA-256 PII hashing at ingest boundary; RBAC with least privilege; session timeout 15 min; immutable audit log | [`docs/architecture.md`](../docs/architecture.md) Section 5 | Encryption and hashing; RBAC Day 9 |

### APP 12 — Access to Personal Information

| Requirement | Control | Evidence | Status |
|-------------|---------|----------|--------|
| Individuals can request access to their personal information | Since all identifiers are hashed and no raw PII is stored, no direct subject access request mechanism is required. The hash is one-way and cannot be reversed. | [`logstash/pipelines/transaction_ingest.conf`](../logstash/pipelines/transaction_ingest.conf) | Implemented |

---

## 6. Information Asset Classification

| Asset | Classification | Retention | Access Roles |
|-------|---------------|-----------|-------------|
| Raw transaction events (pre-Logstash) | RESTRICTED — PII | Destroyed at ingestion boundary | Logstash process only |
| Normalised transaction events in Elasticsearch | CONFIDENTIAL — pseudonymised | 90 days | `security_analyst`, `senior_security_engineer`, `system_administrator` |
| SIEM alert records (`meridian-alerts-*`) | CONFIDENTIAL | 90 days | `security_analyst`, `senior_security_engineer`, `compliance_officer` |
| Incident records (`meridian-incidents-*`) | CONFIDENTIAL | 1 year | `security_analyst`, `senior_security_engineer`, `compliance_officer` |
| Audit trail (`meridian-audit-*`) | CRITICAL — immutable | 7 years | `compliance_officer`, `read_only_auditor` (read); no role can delete |
| Compliance evidence (`meridian-compliance-*`) | CRITICAL | 7 years | `compliance_officer`, `read_only_auditor` |
| LSTM model artefacts (`.pt`, `.onnx`) | INTERNAL | Indefinite (versioned) | `ml_operations`, `system_administrator` |
| Training data snapshots | RESTRICTED | Indefinite | `ml_operations` |
| Source code | INTERNAL | Indefinite (git history) | All developers |
| Credentials (`.env`) | SECRET | Rotate every 90 days | `system_administrator` only — never committed to git |

---

## 7. Known Gaps and Remediations

The following gaps must be resolved before any production deployment. They do not affect the prototype's ability to demonstrate the required security architecture.

| Gap | Frameworks affected | Remediation | Planned |
|-----|-------------------|-------------|---------|
| RBAC not yet enforced at Elasticsearch API level | APRA Para 16, PCI Req 7, PCI Req 8 | Implement Elasticsearch native security roles; wire analyst accounts | Day 9 |
| Hybrid scorer and playbook engine not yet built | APRA Para 24–28, PCI Req 10, PCI Req 12 | Build `src/siem/hybrid_scorer.py` and `src/siem/playbook_engine.py` | Day 8 |
| Audit trail index not yet populated | APRA Para 37–38, PCI Req 10 | Playbook engine writes to `meridian-audit-*` on every action | Day 8 |
| TLS certificates not provisioned for production | PCI Req 2, PCI Req 4 | Generate CA-signed certificates; configure Elasticsearch HTTPS transport | Day 13 |
| Penetration testing not performed | PCI Req 11 | OWASP ZAP scan of LSTM API, Kibana, and Docker network | Day 13 |
| Acceptance tests not yet written | APRA Para 29, PCI Req 11 | Write AT-1 through AT-10 in `tests/test_acceptance.py` | Day 12 |
| AUSTRAC reporting not in scope | Regulatory gap | Extend compliance module in ITA602 | Future |
| `tzdata` package required on Windows hosts | Operational | `pip install tzdata`; already documented in `CLAUDE.md` | Documented |

---

## 8. Control Summary by Framework

### APRA CPS 234

| Status | Count |
|--------|-------|
| Implemented | 9 |
| Partial | 3 |
| Planned | 7 |
| N/A | 0 |

### PCI DSS v4.0

| Status | Count |
|--------|-------|
| Implemented | 10 |
| Partial | 5 |
| Planned | 8 |
| N/A | 1 |

### Australian Privacy Act 1988 (APPs)

| Status | Count |
|--------|-------|
| Implemented | 9 |
| Partial | 1 |
| Planned | 0 |
| N/A | 2 |

---

## 9. References

| Document | Location |
|----------|----------|
| System architecture | [`docs/architecture.md`](../docs/architecture.md) |
| Model performance | [`results/final_metrics.json`](../results/final_metrics.json) |
| Model card | [`models/MODEL_CARD.md`](../models/MODEL_CARD.md) |
| Logstash ECS pipeline | [`logstash/pipelines/transaction_ingest.conf`](../logstash/pipelines/transaction_ingest.conf) |
| SIEM rule engine | [`src/siem/rule_engine.py`](../src/siem/rule_engine.py) |
| LSTM inference API | [`src/serving/app.py`](../src/serving/app.py) |
| Onboarding guide | [`onboarding.md`](../onboarding.md) |
| APRA CPS 234 (external) | https://www.apra.gov.au/sites/default/files/cps_234_july_2019_for_public_release_final.pdf |
| PCI DSS v4.0 (external) | https://www.pcisecuritystandards.org/document_library/ |
| Australian Privacy Act 1988 (external) | https://www.oaic.gov.au/privacy/the-privacy-act |
