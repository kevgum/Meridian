# Meridian Sentinel — Implementation Evidence

Screenshots captured from the **running system** on 2026-08-16 10:52 UTC.
Nothing here is mocked. Every value is produced by executing the real pipeline.

**Traced transaction (screenshots 01–10, 13–15):** `TXN-1D55ED7550D04D20`
CUST-24417 · A$18,169.80 · TRANSFER to watchlisted merchant M7891 · Perth, WA
Inference request: `INF-6EC1C7B4225B4C8C`

**SAFE transaction (screenshot 11):** `TXN-91406653E26545C2` — CUST-52210 · A$50.00

| # | File | What it proves |
|---|------|----------------|
| 01 | 01-transaction-ingestion.png | A real transaction enters the pipeline and is assigned a correlation id |
| 02 | 02-data-ingestion-normalisation.png | Normalisation into dual-shape (flat + nested ECS) document |
| 03 | 03-feature-engineering.png | Raw history → 5×13 MinMax-scaled tensor |
| 04 | 04-redis-not-implemented.png | Redis is absent; history comes from authoritative data |
| 05 | 05-rule-engine.png | All 5 rules evaluated, pass/FAIL each, with evidence |
| 06 | 06-lstm-inference.png | Real inference call + tensor dimensions (tokens N/A) |
| 07 | 07-lstm-behaviour-analysis.png | Sequence scored per payment; documented model limit |
| 08 | 08-hybrid-threat-score.png | threat = LSTM×0.60 + SIEM×0.40, real values |
| 09 | 09-final-verdict.png | Final verdict vs threshold |
| 10 | 10-suspicious-playbook.png | Playbook fires, incident created, LOCK_ACCOUNT |
| 11 | 11-safe-transaction.png | Legitimate transaction, no incident |
| 12 | 12-react-dashboard.png | **Live browser capture** of the React dashboard |
| 13 | 13-elasticsearch-event.png | Document persisted and retrievable from Elasticsearch |
| 14 | 14-audit-logs.png | 8-stage audit trail under one correlation id |
| 15 | 15-end-to-end-flow.png | Whole pipeline joined by one id |
| 16 | 16-model-status-inference-log.png | **Live browser capture** of the model status endpoint: tensor sizes + rolling inference log |
| 17 | 17-elasticsearch-browser.png | **Live browser capture** of the Elasticsearch REST API returning the traced document |

| 18 | 18-kibana-discover-transaction.png | **Live Kibana Discover** — the traced transaction, 1 hit, all 38 fields |
| 19 | 19-kibana-audit-trail.png | **Live Kibana Discover** — all 8 audit stages for the same correlation id |
| 20 | 20-react-dashboard-transaction.png | **Live dashboard** — per-transaction investigation drawer with score breakdown |

Screenshots 16-20 are additional live browser captures. Every one carries an
explanation cell above the frame stating what it proves; screenshots 01-15 carry
the same explanation in their own header.
16 is `http://lstm-serving:8080/v1/models/lstm?limit=20&pretty`.
17 queries `correlation_id.keyword:"TXN-A5CB1EDB008D44BC"` and returns exactly 1 hit.
18 and 19 are **real Kibana Discover** captures, time range "Last 24 hours",
queried by `correlation_id:"TXN-A5CB1EDB008D44BC"` — 18 on the meridian-transactions-* data
view, 19 on Meridian Audit Trail showing all 8 stages.
Kibana rejects credentials in a URL, so these were captured by logging in
through Kibana's own login API and injecting the returned session cookie via
the Chrome DevTools Protocol. No password appears in any URL or image.
Screenshots 16-19 use a separate demo run from 01-15, hence a different id.

## Deviations from the proposed architecture

| Proposed | Implemented | Evidence |
|---|---|---|
| Redis cache (last 5 txns) | **Not implemented** — history read from authoritative transaction data | 04 |
| Elastic Beats | **Not deployed** | 02 |
| Logstash ingestion | Deployed, but demo path writes to ES directly from Python | 02 |
| 12 features / 5×12 | **13 features / 5×13** (geo_velocity_kmh added) | 03, 06 |
| 4 SIEM rules | **5 rules** (RULE_005 burst velocity added) | 05 |
| S3 cold store | **Not implemented** | — |
| LSTM catches slow burn | LSTM does **not**; SIEM Rule 5 does | 07 |

## Token accounting

**LSTM inference uses numerical tensors, not language-model tokens.**
This project contains no LLM component, so no token counts exist anywhere.
Equivalent measures (reported by the API itself):

- Input shape `[1, 5, 13]` = **65 float32 values** per sequence
- Output shape `[1, 1]` = **1 scalar** (anomaly probability)
- Tensor names: `transaction_sequence` → `anomaly_logit`

## Reproduce

```
docker compose up -d
docker compose --profile dev run --rm -e ELASTIC_HOST=http://elasticsearch:9200     dev python -m scripts.end_to_end_demo --write --full-doc
```

Raw captured output is in `evidence/raw/`; source pages in `evidence/pages/`.
