# Security Review — Meridian Sentinel

**Day:** 13 — Security Review and Hardening Notes  
**Date:** 2026-06-30  
**Branch:** `feature/day13-security-merge`

---

## 1. Credential / Secret Scan

### Method
- Grep scan for hardcoded credential patterns (`password=`, `secret=`, `api_key=`, AWS keys, private key headers) across `.py`, `.ts`, `.tsx`, `.yaml`, `.yml`, `.conf`, `.json`, `.md` files
- `git ls-files` check for any tracked `.env`, `certs/*.key`, `certs/*.crt`, or `models/*.onnx` files

### Findings

| Check | Result |
|-------|--------|
| `.env` tracked by git | Not tracked — only `.env.example` |
| `certs/*.key`, `certs/*.crt` tracked | Not tracked |
| `models/*.onnx` tracked | Not tracked (generated at container startup) |
| Hardcoded production credentials | None found |
| AWS access keys / GitHub tokens | None found |
| Private key material in repo | None found |

### `meridian123` Occurrences

The string `meridian123` (default prototype Elasticsearch password) appears in 12 files, all as one of:

1. **Environment variable fallback** — `os.environ.get("ELASTIC_PASSWORD", "meridian123")` in Python source. The real value is always read from `.env` at runtime; `meridian123` is only the fallback when no environment variable is set.
2. **Docker Compose default interpolation** — `${ELASTIC_PASSWORD:-meridian123}` in `docker-compose.yml`. Same pattern — overridden by `.env`.
3. **Documentation** — `CLAUDE.md`, `README.md`, `onboarding.md` document the known prototype default credentials for local development.

**Verdict:** Acceptable for a prototype. This is the documented, intentional default for local Docker development — not a leaked production secret. `.env` (which would hold a real production password) is correctly gitignored.

**Hardening note for production:** Remove the `meridian123` fallback default entirely and require `ELASTIC_PASSWORD` to be set, failing fast if absent.

---

## 2. OWASP ZAP Baseline Scan

**Target:** `https://meridan-five.vercel.app` (deployed React SOC dashboard)  
**Scan type:** Baseline (passive only — no active attack traffic)  
**Tool:** `ghcr.io/zaproxy/zaproxy:stable zap-baseline.py`  
**Report:** [`results/zap_report.html`](zap_report.html)

See `zap_report.html` for full findings. Summary and remediation below.

### Actual Scan Result

```
Total of 8 URLs
FAIL-NEW: 0    FAIL-INPROG: 0    WARN-NEW: 6    WARN-INPROG: 0    INFO: 0    IGNORE: 0    PASS: 60
```

**0 failures. 6 warnings, all low-severity missing-header findings typical of an unconfigured SPA deployment.**

| Finding | Rule ID | Severity | Remediation |
|---------|---------|----------|--------------|
| Missing Anti-clickjacking Header (`X-Frame-Options`) | 10020 | Low | Add via `vercel.json` headers |
| `X-Content-Type-Options` Header Missing | 10021 | Low | Add via `vercel.json` headers |
| Content Security Policy (CSP) Header Not Set | 10038 | Low/Informational | Add via `vercel.json` headers |
| Permissions Policy Header Not Set | 10063 | Informational | Add via `vercel.json` headers |
| Cross-Domain Misconfiguration | 10098 | Low | Review CORS config (Vercel default — static asset CORS is benign here) |
| Cross-Origin-Embedder-Policy Header Missing or Invalid | 90004 | Informational | Add via `vercel.json` headers |

### Out of Scope for This Scan

- LSTM Inference API (`localhost:8080`) — not internet-exposed, no public endpoint
- Elasticsearch (`localhost:9200`) — not internet-exposed, RBAC-protected
- These services only run inside the local Docker stack; ZAP can only reach the Vercel-deployed frontend

### Recommended Hardening (Production)

Add to `frontend/vercel.json`:

```json
{
  "rewrites": [{ "source": "/(.*)", "destination": "/index.html" }],
  "headers": [
    {
      "source": "/(.*)",
      "headers": [
        { "key": "X-Frame-Options", "value": "DENY" },
        { "key": "X-Content-Type-Options", "value": "nosniff" },
        { "key": "Referrer-Policy", "value": "strict-origin-when-cross-origin" },
        { "key": "Permissions-Policy", "value": "geolocation=(), microphone=(), camera=()" }
      ]
    }
  ]
}
```

This is documented as a hardening recommendation, not applied in this prototype — the dashboard currently serves only mock/demo data with no authentication, so the risk is low for the ITW601 submission scope.

---

## 3. Summary

| Area | Status |
|------|--------|
| No committed credentials, keys, or certs | Pass |
| `.env` correctly gitignored | Pass |
| ZAP baseline scan completed | Pass — 0 FAIL, 6 WARN (low/info), 60 PASS — see `zap_report.html` |
| Findings requiring immediate fix | None — all 6 warnings are low/informational missing-header findings |
| Hardening notes documented for production | See sections above |

This prototype is acceptable for submission as-is. The findings above are standard for any SPA deployed without a custom CDN security header configuration and do not represent exploitable vulnerabilities in the current mock-data demo state.
