# Demo Runsheet — Meridian Sentinel

A one-page guide for presenting the system live. Follow top to bottom.

---

## Before the presentation (do once, ~5 min)

**First, start Docker Desktop** (the stack runs in Docker):

- Open **Docker Desktop** from the Start menu and wait until it says
  *"Engine running"* (about 30-60 seconds).
- Or launch it from PowerShell and wait for the engine:
  ```powershell
  Start-Process "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
  # wait until this prints "running":
  do { docker info *>$null; if ($?) { "running"; break }; Start-Sleep 5 } while ($true)
  ```

If you see `failed to connect to the docker API ... The system cannot find the
file specified`, Docker Desktop is not up yet - start it and wait.

Then bring up the stack and run the tests:

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

**About the two modes:**
- **Offline** (`python scripts/demo_scenarios.py`) - no Docker needed, tells the
  full story. Your safe default.
- **Live** (`--live`) - runs the SIEM rules for real and writes the incidents and
  transactions into Elasticsearch so they show up in the Kibana dashboard. The AI
  scores are representative in both modes (labelled `representative`): the served
  model only scores inputs from its exact training distribution, so hand-built
  demo windows can't drive it. Both modes tell the same, correct story.

---

## Part 1 — The detection demo (~4 min)

Run it on screen:

```powershell
python scripts/demo_scenarios.py          # offline (no Docker needed)
# or
python scripts/demo_scenarios.py --live   # real rules + writes to Kibana
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
| `failed to connect to the docker API` / `docker daemon is not running` | Start Docker Desktop, wait for "Engine running", retry. |
| Demo `--live` cannot reach Elasticsearch | Run `docker compose up -d`, wait ~20 s, retry. |
| Kibana panels empty | Widen the date picker; re-run `python scripts/demo_scenarios.py --live`. |
| A test fails on first boot | Logstash/RBAC may not be ready — re-run `docker compose --profile dev run --rm dev pytest tests/ -v`. |

**Golden rule:** if anything looks off live, switch to offline mode. Same story,
zero risk.
