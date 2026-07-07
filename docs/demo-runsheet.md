# Demo Runsheet — Meridian Sentinel

A one-page guide for presenting the system live. Follow top to bottom.

---

## Before the presentation (do once, ~5 min)

```powershell
# 1. Start the whole stack and run the tests
.\start.ps1

# 2. Create the roles/users (needed for the RBAC part of the tests)
python scripts/bootstrap_rbac.py

# 3. Rehearse the live demo once so you know the real AI scores
python scripts/demo_scenarios.py --live
```

Then import the Kibana dashboard once (Kibana -> Stack Management -> Saved Objects
-> Import -> `kibana/meridian_overview.ndjson`). Full steps: [../kibana/README.md](../kibana/README.md).

**Decide your demo mode from the rehearsal:**
- If scenario 2 (slow burn) shows an AI score >= 0.70 in `--live`, present in live mode.
- If it shows < 0.70, present the **offline** demo (`python scripts/demo_scenarios.py`)
  for the story and use `--live` only to populate Kibana. The offline story is
  identical and always correct.

---

## Part 1 — The detection demo (~4 min)

Run it on screen:

```powershell
python scripts/demo_scenarios.py          # offline (guaranteed clean)
# or
python scripts/demo_scenarios.py --live   # live model + writes to Kibana
```

Walk through the six scenarios. What to say for each:

| Scenario | The point to make |
|----------|-------------------|
| 1. Everyday payment | "This is normal. Nothing fires, nothing happens." |
| 2. **Slow burn** | "No rule is broken - yet the AI flags it. A rules-only bank misses this. **This is the headline.**" |
| 3. Odd hour only | "One weak signal alone is not enough. It stays under watch. This keeps false alarms down." |
| 4. Known-bad merchant only | "Same idea - one rule raises suspicion but does not lock the account on its own." |
| 5. **Impossible travel** | "Sydney to London in 30 minutes - 34,000 km/h. Three rules stack and the account is locked." |
| 6. Coordinated attack | "Every warning at once - top urgency, CRITICAL." |

**The one idea to land:** security rules can only push the risk part-way (they are
40% of the score). The system waits for the AI to agree, or for several rules to
stack, before it acts. Two engines that complement each other.

---

## Part 2 — The Kibana dashboard (~2 min)

Menu -> Dashboard -> **Meridian Sentinel - Fraud Detection Overview**.
(If panels look empty, widen the date picker to *Last 30 days*.)

Point at, in order:
1. The three big numbers — payments checked, suspected fraud, incidents raised.
2. The **Legitimate vs Suspected Fraud** donut — green is safe, red is flagged.
3. **Latest Security Incidents** — the flagged cases from the demo you just ran.

Say: "This is what an analyst sees. Everything here is plain language - no code."

---

## Part 3 — The analyst dashboard (optional, ~2 min)

```powershell
cd frontend
npm run dev        # http://localhost:5173
```

Show the alert queue and click **Investigate** on the flagged case to open the
drawer. Point at "How the Risk Score Adds Up" — the AI counted at 60% plus the
security rules at 40%.

---

## If something breaks

| Problem | Fix |
|---------|-----|
| `docker daemon is not running` | Start Docker Desktop, wait, retry `.\start.ps1`. |
| Demo `--live` cannot reach Elasticsearch | Run `docker compose up -d`, wait ~20 s, retry. |
| Kibana panels empty | Widen the date picker; re-run `python scripts/demo_scenarios.py --live`. |
| Live AI scores look wrong | Fall back to offline: `python scripts/demo_scenarios.py`. |
| A test fails on first boot | Logstash/RBAC may not be ready — re-run `docker compose --profile dev run --rm dev pytest tests/ -v`. |

**Golden rule:** if anything looks off live, switch to offline mode. Same story,
zero risk.
