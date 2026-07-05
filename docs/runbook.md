# Operations Runbook — Meridian Sentinel

> Audience: whoever is operating the stack — starting it, stopping it, bootstrapping RBAC,
> retraining the model, or responding to a fired playbook. Procedural, not architectural —
> see [architecture.md](architecture.md) for system design.

---

## 1. Starting the Stack

### One-command startup (recommended)

```powershell
.\start.ps1          # Windows
```
```bash
./start.sh           # Mac/Linux
```

This creates `.env` from `.env.example`, creates `models/serving/lstm_v1/`, builds all Docker images, starts Elasticsearch/Kibana/Logstash/lstm-serving, waits for health checks, and runs the test suite.

### Manual startup

```bash
cp .env.example .env
mkdir -p models/serving/lstm_v1
docker compose --profile dev build
docker compose up -d elasticsearch kibana logstash lstm-serving
docker compose ps                          # confirm all show "healthy"
```

### First-time-only: bootstrap RBAC

Must run once after the stack's first start (or any time you wipe the ES data volume):

```bash
pip install elasticsearch==8.11.0
$env:PYTHONIOENCODING = "utf-8"            # Windows only — box-drawing chars in output
python scripts/bootstrap_rbac.py
```

This creates 6 roles, 6 test users, a scoped API key for the feature-engineering service, and a Kibana service account token. **Copy the printed `KIBANA_SERVICE_TOKEN` value into `.env`, then restart Kibana:**

```bash
docker compose restart kibana
```

Without this token, Kibana exits with code 78 (ES 8.11+ forbids the `elastic` superuser as the Kibana credential).

---

## 2. Stopping the Stack

```bash
docker compose down            # stop containers, keep ES data volume
docker compose down -v         # stop containers AND delete ES data (full reset — re-run bootstrap_rbac.py after)
```

---

## 3. Health Checks

```bash
docker compose ps                                  # all services should show "healthy"
curl http://localhost:8080/v1/models/lstm           # LSTM serving status
curl -u elastic:meridian123 http://localhost:9200/_cluster/health | grep status   # green/yellow
docker compose logs <service> --tail 50             # service-specific logs
```

| Service | Port | Healthy looks like |
|---------|------|---------------------|
| LSTM Inference API | 8080 | `curl /v1/models/lstm` returns 200 |
| Elasticsearch | 9200 | `_cluster/health` status green/yellow |
| Kibana | 5601 | Login page loads (requires service token in `.env`) |
| Logstash | 5000 (TCP) | No `xpack.monitoring` 401 errors in logs |

---

## 4. Running the Acceptance Suite

```bash
# Full 35 tests — requires the stack up and bootstrap_rbac.py already run
docker compose --profile dev run --rm dev pytest tests/test_acceptance.py -v

# 32 unit-only tests — no Docker stack required
docker compose --profile dev run --rm dev pytest tests/test_acceptance.py -v -m "not integration"
```

Expected: `35 passed in ~3.5s`. See [results/acceptance_test_report.md](../results/acceptance_test_report.md) for the full evidence trail per test.

---

## 5. Retraining the Model

The LSTM is trained in Google Colab (GPU required), not locally. Full walkthrough: [colab-guide.md](colab-guide.md).

**Summary:**
1. Open `notebooks/02_lstm_model.ipynb` in Colab, set runtime to GPU (T4)
2. Run the full 35-epoch training run with `pos_weight=1.0` and `WeightedRandomSampler` — **do not** revert to a fixed `pos_weight=773`; this previously caused the model to collapse to predicting "not fraud" for everything (see [training-notes.md](training-notes.md))
3. Run `03_evaluation.ipynb` — cell 16 sweeps thresholds and auto-selects the lowest one meeting the 98.55% accuracy target (currently `0.92`), then exports to ONNX
4. Download and place locally:
   - `models/lstm_checkpoint_best.pt`
   - `models/lstm_final.pt`
   - `results/training_history.json`
   - `results/final_metrics.json`
   - `results/figures/`
5. Restart `lstm-serving` so it reconverts the new checkpoint to ONNX:
   ```bash
   rm models/serving/lstm_v1/lstm_fraud_detector.onnx
   docker compose restart lstm-serving
   ```
6. Re-run the acceptance suite before promoting — confirm accuracy ≥ 98.55% target (current: 98.86%) and check FPR against the ≤ 0.50% target (current: 1.10% — improved but not met) per [models/MODEL_CARD.md](../models/MODEL_CARD.md). If metrics regress, do not promote — revert to the previous `lstm_checkpoint_best.pt`.

---

## 6. Incident Response (Playbook Firing)

When the hybrid threat scorer fires (`threat_score ≥ 0.70`, or `lstm_score ≥ 0.70` via the LSTM_ALONE path), the playbook engine automatically:

1. Sets the incident `action = LOCK_ACCOUNT`
2. Writes an incident record to `meridian-incidents-YYYY.MM.dd` in Elasticsearch
3. Emits a mock analyst notification via `logger.warning("INCIDENT CREATED | id=... | customer=... | severity=... | threat_score=... | trigger=... | action=...")`

**Analyst response procedure:** see [analyst-guide.md](analyst-guide.md) Section 4–5 for the dashboard triage workflow (Confirm Threat / Investigate).

**Manually unlocking a falsely-locked account** (prototype has no dashboard control for this — direct ES action):

```bash
curl -u elastic:$ELASTIC_PASSWORD -X POST "http://localhost:9200/meridian-incidents-*/_update_by_query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": { "term": { "incident_id": "<INCIDENT_ID>" } },
    "script": { "source": "ctx._source.status = '\''CLOSED_FALSE_POSITIVE'\''; ctx._source.closed_by = '\''<your_analyst_id>'\''" }
  }'
```

Replace `<INCIDENT_ID>` and `<your_analyst_id>`. This writes to the immutable audit trail rather than deleting the record — never delete incident documents.

---

## 7. Common Failures and Fixes

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| Kibana exits with code 78 | ES 8.11+ forbids `elastic` superuser for Kibana | Run `bootstrap_rbac.py`, copy `KIBANA_SERVICE_TOKEN` into `.env`, `docker compose restart kibana` |
| Logstash exits with code 1, parse error | Comments/blank lines inside a `{ }` hash block in the pipeline config | Logstash 8.11's DSL parser rejects these — keep hash blocks free of comments and blank lines |
| Logstash logs show repeated 401s | `xpack.monitoring` trying to reach ES without credentials | Confirm `xpack.monitoring.enabled=false` is set on the logstash service in `docker-compose.yml` |
| `ConnectionRefusedError` from inside the `dev` container | Code defaulting to `localhost` for a service that's actually another container | Use the Docker service name (`elasticsearch`, `logstash`, `lstm-serving`), not `localhost`, for any inter-container call |
| `AuthorizationException` 403 on ES index write | `security_analyst` role has `write`/`create`/`index` but not `create_index`/`auto_configure` | Pre-create the index as `elastic` admin before the analyst user writes to it (this is intentional least-privilege — see [architecture.md](architecture.md) RBAC section) |
| ONNX file missing or < 100 KB | Corrupted conversion at container startup | `rm models/serving/lstm_v1/lstm_fraud_detector.onnx && docker compose restart lstm-serving` |
| Elasticsearch exits with code 137 | Out of memory | Increase Docker Desktop memory to ≥ 4 GB |
| `UnicodeEncodeError` running Python scripts on Windows | Box-drawing characters default to cp1252 | `$env:PYTHONIOENCODING = "utf-8"` before running the script |

---

## 8. Security Operations

- **Credentials** — all come from `.env` (copied from `.env.example`), never hardcoded. `.env` is gitignored.
- **Periodic re-scan** — re-run the credential/secret scan and OWASP ZAP baseline (see [results/security_review.md](../results/security_review.md)) after any dependency bump or before a new tagged release:
  ```bash
  docker run --rm -v "$(pwd)/results:/zap/wrk" ghcr.io/zaproxy/zaproxy:stable \
    zap-baseline.py -t <deployed-dashboard-url> -r zap_report.html
  ```
- **Analyst webhook notifications** — set `ANALYST_WEBHOOK_URL` in `.env` to route playbook notifications to Teams, Slack, or PagerDuty. Leave empty for log-only mode.

### Enabling TLS 1.3 (PCI DSS Req 4.2.1)

A `docker-compose.tls.yml` overlay and `scripts/generate_certs.sh` are provided. Steps:

```bash
# 1. Generate self-signed CA + ES server certificate (requires openssl)
chmod +x scripts/generate_certs.sh
./scripts/generate_certs.sh
# Output: certs/ca.crt, certs/elasticsearch.crt, certs/elasticsearch.key

# 2. Update .env
ELASTIC_HOST=https://localhost:9200

# 3. Start the stack with the TLS overlay
docker compose -f docker-compose.yml -f docker-compose.tls.yml up -d

# 4. Re-run RBAC bootstrap (ES is now on HTTPS)
python scripts/bootstrap_rbac.py
```

The overlay enables:
- `xpack.security.http.ssl` on Elasticsearch with TLSv1.3 minimum
- Kibana's `ELASTICSEARCH_HOSTS` updated to `https://`
- CA cert mounted into all containers that connect to ES

**Logstash note:** the Logstash pipeline uses a hardcoded `http://` host. For full TLS, create a separate `logstash/pipelines/transaction_ingest_tls.conf` with `ssl_enabled => true` and `ssl_certificate_authorities => ["/usr/share/logstash/config/certs/ca.crt"]` and mount it instead.

**Production note:** replace the self-signed certs with certificates from a trusted CA (Let's Encrypt, AWS ACM, or corporate PKI) before any production deployment.

---

## 9. Release Procedure

1. Confirm `pytest tests/test_acceptance.py -v` → 35/35 PASS
2. Run/update the security review (Section 8)
3. Update `CLAUDE.md` and `docs/PROJECT_BOARD.md` status tables
4. Merge the feature branch into `main` (fast-forward where possible)
5. Tag: `git tag -a vX.Y.Z-prototype -m "<summary>"`
6. Push: `git push origin main && git push origin vX.Y.Z-prototype`
