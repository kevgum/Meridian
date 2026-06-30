# Analyst Guide — Meridian Sentinel SOC Dashboard

> Audience: security analysts triaging fraud alerts on the Meridian Sentinel dashboard.  
> No coding knowledge required. This guide covers what each panel shows, how to read a
> threat score, and the exact steps to confirm or dismiss an alert.

---

## 1. Logging In and Layout

Open the dashboard at the deployed Vercel URL (or `http://localhost:5173` in local dev).

The **top bar** shows:
- **Connection status** — a green indicator reading "Connected to live Elasticsearch" means you're seeing real transaction data; "Demo mode — mock data" means the dashboard is running standalone (e.g. on Vercel without a live backend) and is showing illustrative data only.
- **Session timer** — your session automatically signs you out after 15 minutes of inactivity (PCI DSS Req 8.2.8). You'll get a 60-second warning with a countdown before this happens — move your mouse, click, or press a key to stay logged in.

The dashboard has four main panels: **Transaction Feed**, **Detection Panel**, **Alert Queue**, and **Compliance Badges**, plus a slide-in **Investigation Drawer** for deep-dives.

---

## 2. Transaction Feed (left panel)

A live, scrolling list of incoming transactions, most recent first. Each row shows:
- Customer and merchant
- Amount
- LSTM anomaly score as a percentage bar (`aria-label="LSTM anomaly score X%"`)
- A green **PASS** badge if the SIEM rules did not fire on that transaction

This panel is your situational awareness feed — most rows will be unremarkable. You're watching for rows with a high anomaly score bar or a missing PASS badge.

---

## 3. Detection Panel (centre)

When you select a transaction (or it's the active alert), this panel shows the **Anomaly Probability** — the raw LSTM sigmoid output for that transaction sequence — and a breakdown of **Behavioural Signals** that contributed to the score (amount deviation, geo-velocity, off-hours activity, transaction frequency, etc.).

This is the "why did the model flag this" view. Use it to sanity-check the alert before acting.

---

## 4. Alert Queue (right panel) — your primary triage workflow

This is where active, unresolved alerts live. Each alert card shows three scores:

| Label | What it means |
|-------|--------------|
| **LSTM** | The neural network's anomaly probability (0.00–1.00) |
| **SIEM** | The rule engine's normalised score: 0 rules fired = 0.00, 1 = 0.33, 2 = 0.67, 3+ = 1.00 |
| **Hybrid** | `(LSTM × 0.60) + (SIEM × 0.40)` — the combined threat score that drives the verdict |

**Status badges:**
- **MONITOR** (blue) — hybrid score below 0.70. Logged for visibility, no automatic action taken. You can still investigate manually if something looks off.
- A fired alert (no MONITOR badge) means the playbook already executed automatically — see Section 5.

Each alert also shows an **SLA countdown** — the time remaining to respond per your incident response policy. Don't let this hit zero; escalate if you're unsure.

### Triage actions

Two buttons appear on each active alert:

1. **"Confirm Threat"** — confirms this is genuine fraud and locks the customer's account (if not already locked by the automated playbook). Once clicked, the button updates to "Threat confirmed" and the action is written to the immutable audit index (`meridian-incidents-*`) with your analyst ID and timestamp.
2. **"Investigate"** — opens the Investigation Drawer (Section 5) for a deeper look before you decide.

**Always investigate before confirming** unless the evidence is unambiguous (e.g. a watchlist merchant hit plus an extreme LSTM score).

---

## 5. Worked Example: CUST-18656

This is the reference scenario used throughout testing and documentation. Walking through it teaches you how to read a real (if synthetic) alert.

**Customer:** CUST-18656, Darwin NT  
**Activity:** 6 transactions in 75 minutes, alternating Online/Card, electronics + restaurant merchants, total A$665.20

**What the engines saw:**

| Engine | Result |
|--------|--------|
| SIEM Rule 1 (amount > $10,000) | PASS — largest transaction was $256.74 |
| SIEM Rule 2 (geo-velocity > 500 km/h) | PASS — all transactions in Darwin, no location jump |
| SIEM Rule 3 (off-hours) | PASS — all within business hours |
| SIEM Rule 4 (watchlist merchant) | PASS — merchant not on the watchlist |
| **SIEM score** | **0.00** (0 of 4 rules fired) |
| **LSTM anomaly probability** | **0.74** — the model flagged a behavioural pattern none of the 4 hard rules could see |
| **Hybrid score** | `(0.74 × 0.60) + (0.00 × 0.40) = 0.444` — below the 0.70 hybrid threshold |

**Why did this still fire?** Meridian Sentinel has a second trigger path: **LSTM_ALONE**. If the LSTM score alone is ≥ 0.70, the playbook fires even if the hybrid score is below 0.70 and SIEM saw nothing. This exists because a sufficiently confident neural-network signal shouldn't be diluted away by an unrelated rule engine score of zero — rules can't catch everything, and this is exactly the class of fraud they're blind to.

**Resulting action:** `LOCK_ACCOUNT`, severity `HIGH`, incident opened in `meridian-incidents-*`, analyst notified.

**As the analyst, what do you do?**
1. Open the Investigation Drawer for CUST-18656 — review the transaction timeline table (time, merchant, amount, LSTM score per transaction) and the score breakdown (LSTM score/contribution, SIEM score/contribution, hybrid score).
2. Note that all 4 SIEM rules legitimately passed — there's no rule-based red flag, only the behavioural signal.
3. Decide: does the LSTM-flagged pattern (rapid alternating purchases at the same two merchant categories) look like genuine fraud, or could it be an explainable pattern (e.g. a customer doing routine same-day shopping)?
4. If you assess it as fraud, click **Confirm Threat** to close the loop and lock in the audit record. If you assess it as a false positive, follow your incident response policy for releasing the account lock (outside the scope of this dashboard — see [runbook.md](runbook.md) for the manual unlock procedure).

---

## 6. Investigation Drawer

Opens from the right edge of the screen. Contains:
- **Customer summary** — location, time window, total transaction value
- **Transaction timeline table** — every transaction in the sequence with time, merchant, amount, and per-transaction LSTM score
- **Score breakdown** — LSTM score and its weighted contribution, SIEM score and its weighted contribution, and the final hybrid score

Press **Escape** or click the close button (top-right) to dismiss. Focus returns to the alert you were viewing — the drawer is fully keyboard-navigable (WCAG 2.2 AA).

---

## 7. Compliance Badges

A footer panel showing which compliance frameworks this prototype maps controls against: **APRA CPS 234**, **PCI DSS v4.0**, **Australian Privacy Act 1988**. This is informational — it confirms the system you're using has documented compliance controls, not something you interact with during triage. Full control mapping: [compliance/control_mapping.md](../compliance/control_mapping.md).

---

## 8. Accessibility Notes

The dashboard is built to WCAG 2.2 Level AA:
- Every interactive element is reachable by keyboard (Tab/Shift+Tab) and operable with Enter/Space
- Score updates and new alerts are announced to screen readers via a visually-hidden `aria-live="polite"` region — you don't need to be staring at the screen to know a new alert arrived
- No information is conveyed by colour alone — status badges always carry text (MONITOR, PASS, etc.)
- Focus is trapped inside modals (session warning) and the investigation drawer while open, and returns to the triggering element on close

If you use a screen reader or rely on keyboard-only navigation, you should be able to complete the full triage workflow — confirm, investigate, dismiss — without a mouse.

---

## 9. When in Doubt

This dashboard surfaces evidence; it does not make the final call. If a score looks borderline, the SLA is about to expire, or the evidence is ambiguous, escalate per your organisation's incident response policy rather than guessing. See [runbook.md](runbook.md) Section "Incident Response" for escalation paths in this prototype.
