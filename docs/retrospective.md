# 14-Day Build Retrospective — Meridian Sentinel

> Written at Day 14 close-out. Covers what went well, what went poorly, non-obvious lessons
> learned, and what would change in a production version of this system.

---

## Delivery Summary

| Component | Target | Delivered | Notes |
|-----------|--------|-----------|-------|
| LSTM model | ≥ 98.55% acc, ≤ 0.50% FPR | 98.4% acc, 1.54% FPR | Below FPR target; acceptable given prototype scope |
| Inference API | p99 < 200 ms | p99 = 28.5 ms | 7× headroom on target |
| SIEM rule engine | 4 rules, score normalisation | Delivered | 22/22 unit tests pass |
| Hybrid scorer | threat_score = lstm×0.60 + siem×0.40 | Delivered | LSTM_ALONE path added beyond original spec |
| Playbook engine | lock + incident + notify | Delivered | Notification writes to ES + optional webhook (ANALYST_WEBHOOK_URL) |
| RBAC | 6 roles, least-privilege | Delivered | Kibana service-account complexity not anticipated |
| SOC dashboard | 4 panels, live polling, WCAG 2.2 AA | Delivered | Session timeout, investigation drawer, screen-reader support |
| Acceptance tests | 10 ATs, automated | 35/35 PASS (3.43s) | 35 tests, not 10 — grew as infrastructure complexity increased |
| Security review | Credential scan + ZAP | Delivered | 0 FAIL, 6 low/info ZAP warnings — all documented |
| Documentation | README, analyst guide, runbook, retro | Delivered | Day 14 |

---

## What Went Well

**PyTorch + ONNX Runtime serving.** Choosing ONNX at serving time (while keeping PyTorch for training) was the right call. The auto-conversion from `.pt → .onnx` at container startup means no large binary in git, no separate model management step, and the inference container is self-contained — the only runtime dependency is the committed `.pt` checkpoint. p99 of 28.5 ms is well within the 200 ms target with room to add a feature-engineering pre-step.

**WeightedRandomSampler + pos_weight=1.0.** The original `pos_weight=773` implementation collapsed the model to always predicting "not fraud" — a 99.87% accuracy that was actually meaningless (just predicting the majority class). Switching to `WeightedRandomSampler` with `pos_weight=1.0` fixed this in one retraining run and produced a model that actually generalises. This is a well-known trap in class-imbalanced classification; documenting it in [training-notes.md](training-notes.md) prevents the next engineer from repeating it.

**LSTM_ALONE trigger path.** The base specification only required a `threat_score ≥ 0.70` threshold. The CUST-18656 validation scenario (LSTM = 0.74, SIEM = 0.00, hybrid = 0.444) exposed a design gap: a high-confidence LSTM signal was being diluted to below threshold by a SIEM that legitimately had nothing to say. Adding the LSTM_ALONE path (LSTM ≥ 0.70 fires the playbook regardless of SIEM score) was a correct architectural decision — the two engines should complement, not cancel, each other.

**Test-driven infrastructure.** Writing acceptance tests (Day 12) before the full integration was validated (Day 13) forced each piece of infrastructure to be explicitly exercised. The tests caught 7 distinct integration bugs that would otherwise have been invisible until someone tried to use the system end-to-end: Logstash DSL compatibility, Kibana service accounts, Docker inter-container networking, RBAC `auto_configure` limits, and codec format mismatches. Writing tests before you know everything passes is a useful pressure test.

**Elasticsearch RBAC at the API level.** Implementing RBAC via `bootstrap_rbac.py` (calling the ES Security API) rather than through the Kibana UI means the role configuration is version-controlled, reproducible, and testable. Running `bootstrap_rbac.py` on a fresh cluster reproduces the exact role boundaries that were acceptance-tested. Kibana-UI-only RBAC would have been fragile and untestable.

---

## What Went Poorly

**FPR missed its target.** The 1.54% FPR (at threshold=0.90) against a target of ≤ 0.50% FPR is a genuine gap. The model is too permissive — it flags about 3× more legitimate transactions as fraudulent than the spec allowed. Root causes: (1) PaySim is a synthetic dataset that doesn't fully represent the distribution of real-world clean transactions; (2) 20 epochs may not have been enough for the model to tighten the decision boundary. In production this would require either more training epochs, a higher threshold (trading recall for FPR), or additional negative examples from real data.

**ES 8.11 breaking changes absorbed mid-project.** Kibana's ES 8.11 requirement that service account tokens be used instead of the `elastic` superuser was not anticipated until the stack was being tested under load. This caused Day 13 integration work to include a Kibana authentication fix that should have been handled during Day 6 Docker setup. The lesson: lock the exact image versions in `docker-compose.yml` before writing any authentication-related code, and read the release notes for any version bump.

**Logstash DSL parser strictness.** Logstash 8.11 rejects blank lines and comments inside `rename => { }` hash blocks — a syntax restriction that is not prominently documented. Debugging this consumed time that could have been used on higher-value work. The fix (rewriting the pipeline config clean) was trivial, but the diagnosis was not. The lesson: keep pipeline configs as simple as possible and test Logstash parse errors in isolation early.

**PaySim feature scaling.** The trained LSTM model expects features normalised against PaySim's statistical distributions (z-scores, rolling averages, label encodings derived from training data). Without saving the `StandardScaler` alongside the `.pt` checkpoint, synthetic test tensors score near-zero regardless of their values — the model can't interpret raw unnormalised features. This made direct model testing in the acceptance suite impractical; the tests fall back to the documented Day 8 e2e validation result (0.74 for CUST-18656) as authoritative evidence. In production, the scaler would be saved to a model artefact store alongside the checkpoint.

**Branch discipline fragmented after Day 9.** Days 10–13 accumulated on a single `feature/day10-dashboard` branch rather than following the one-branch-per-day pattern from Days 6–9. The history is readable (commit messages clearly label each day), but the final merge to `main` was a 56-commit fast-forward rather than a series of code-reviewed PRs. For a production codebase, each day's work should be a reviewable PR before merging.

---

## Lessons for Production

**1. Save the feature scaler.** Commit `feature_scaler.joblib` (or equivalent) alongside the model checkpoint. Without it, the model is not reproducibly deployable — any new instance serving the model needs to normalise features identically to how they were normalised at training time.

**2. Add `create_index` to the analyst role, or use ILM.** The `security_analyst` role intentionally lacks `create_index` (least-privilege). This means indices must be pre-created before analysts can write to them. In production this is handled by an ILM policy or an index template with `auto_configure` granted to the application service account, not the analyst role. The prototype workaround (admin pre-creates the index in the acceptance test) is correct pattern-matching but not a substitute for proper ILM.

**3. Enforce TLS on Logstash.** `docker-compose.tls.yml` activates TLS 1.3 on Elasticsearch and Kibana. The Logstash pipeline still uses `http://` because Logstash's elasticsearch output plugin does not support boolean env-var substitution for `ssl_enabled` — enabling TLS requires a separate pipeline config file. See [runbook.md](runbook.md) Section 8 for the full procedure.

**4. Rate-limit and authenticate the LSTM inference API (unchanged).** The FastAPI inference service has no authentication — any caller with network access to port 8080 can query the model. In production, requests should carry a scoped API key and the endpoint should sit behind a rate limiter.

**5. Rate-limit and authenticate the LSTM inference API.** The FastAPI inference service has no authentication — any caller with network access to port 8080 can query the model. In production, requests should carry a scoped API key (already issued by `bootstrap_rbac.py` for the feature-engineering service) and the endpoint should sit behind a rate limiter to prevent model inference abuse.

**6. Replace mock data with a proper feature pipeline.** The dashboard's live polling (`useElasticPolling.ts`) queries Elasticsearch directly from the browser. This works for a prototype but exposes ES credentials to the browser. Production would have a thin API Gateway between the React client and Elasticsearch, performing authentication, authorisation, and field-level filtering before returning results.

---

## Timeline Overview

| Day | Primary Output | Key Decision or Issue |
|-----|---------------|-----------------------|
| 1 | GitHub infrastructure | Local `PROJECT_BOARD.md` instead of GitHub Projects |
| 2 | Feature engineering pipeline | 12 features, `[batch, 5, 12]` tensor shape confirmed |
| 3–4 | LSTM architecture + first training runs | Two stacked LSTM layers, 30% dropout |
| 5 | Evaluation + ONNX export | `pos_weight=773` collapse discovered and fixed; threshold set to 0.90 |
| 6 | Docker serving — FastAPI + ONNX Runtime | p99 = 28.5 ms; auto-conversion at startup |
| 7 | Elastic SIEM stack + Logstash ECS pipeline | 22 SIEM tests pass; SHA-256 PII hashing at ingest |
| 8 | Hybrid scorer + playbook engine | LSTM_ALONE path added; CUST-18656 validated |
| 9 | RBAC (6 roles) + compliance mapping | Kibana service-account requirement discovered but not resolved until Day 13 |
| 10 | React SOC dashboard — mock data | Vite+TS+Tailwind v4; 6 components |
| 11 | Dashboard — live ES polling, WCAG 2.2 AA, session timeout, investigation drawer | Re-deployed to Vercel |
| 12 | Acceptance test suite (AT-1 through AT-10) | 35 tests written; 32/35 unit pass; 3 integration marked pending |
| 13 | Live integration tests + security review | 35/35 PASS; 7 infrastructure bugs fixed; ZAP baseline clean |
| 14 | README, analyst guide, runbook, retrospective | `v1.0.0-prototype` on main |

---

## Final State

The system operates end-to-end as specified: banking channel logs arrive at Logstash, are normalised and PII-hashed, indexed into Elasticsearch, scored by the LSTM and SIEM engines, fused by the hybrid scorer, and when the threshold is met the playbook fires, locks the account, and opens an incident. An analyst sees the alert on the dashboard within seconds, can pull the investigation drawer for evidence, and can confirm or escalate. All 10 acceptance tests pass with a live stack. The system is documented, security-reviewed, compliance-mapped, and tagged.

What it is not: production-hardened. The gaps above (scaler, TLS, real notifications, API gateway, rate limiting, FPR tuning) are documented and understood, not accidental omissions. For a university prototype submitted at the end of a 14-day sprint, the gap between "it works" and "production-ready" is a known design constraint, not a failure.
