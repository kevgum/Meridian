# Meridian Sentinel — Claude AI Assistant Guide

> This file explains how to use Claude (or any AI assistant) effectively across the full 14-day build. It covers session setup, prompt patterns, what Claude can and cannot do, how to interpret responses, and how to stay in control of the project.

---

## What Claude Does in This Project

In this project, **you are the Product Manager and Architect**. Claude is your Senior Software Engineer. The division of responsibilities is:

| You (PM + Architect) | Claude (Senior Software Engineer) |
|---------------------|----------------------------------|
| Decide what to build | Write the complete, working code |
| Read the architecture docs | Follow the architecture specified |
| Copy, paste, and run code | Explain what each piece does |
| Report errors back | Debug and fix the code |
| Confirm outputs match targets | Suggest improvements |
| Make scope decisions | Never make scope decisions |

You do not need to understand every line of code. You need to understand: what each file does, whether the output is correct, and whether it meets the acceptance criteria in `implementation-plan.md`.

---

## How to Start Every Session

Always begin a Claude session with the session initialisation prompt from `agent.md`. Then add today's specific context:

```
Today is Day [X]: [DAY NAME]

Here is what we've completed so far:
[List completed days and their key outputs — e.g. "Day 3: lstm_model.py committed to dev"]

Today's task from our implementation plan:
[Copy the full task description from implementation-plan.md for today's day]

Please confirm you understand the task before writing any code.
```

Having Claude confirm before writing code prevents wasted output and misaligned implementations.

---

## Prompting Principles

### Be Specific About What You Need

**Weak prompt (avoid):**
```
Write the LSTM model
```

**Strong prompt (use):**
```
Write src/models/lstm_model.py — a PyTorch class called LSTMFraudDetector.
Architecture: input [batch, 5, 12] → LSTM 128 units → Dropout 30% → LSTM 64 units → Dropout 30% → Linear 64→1 → Sigmoid.
Include: full PEP 484 type annotations, docstring on every method, exception handlers on forward() for shape mismatches.
The class must be importable from src/models/lstm_model.py.
```

### Always Specify the Output Format

Tell Claude:
- The exact filename and path
- The class or function name
- What it returns
- Where it will be called from

### Ask for One Thing at a Time

One file. One function. One test. Run it. Then ask for the next.

**Why:** Asking for too much at once results in incomplete code, placeholder stubs, or logic errors that are hard to debug.

---

## Handling Claude's Responses

### When the Code Looks Right

1. Copy the entire code block
2. Paste it into the correct file (Google Colab cell, VS Code file, GitHub file creator)
3. Run it immediately
4. If it runs without error → you're done with that piece. Commit it.
5. If it errors → see Error Handling below

### When Claude Explains Something You Don't Understand

You don't need to understand the implementation details. What you need to understand:
- **What does this file do?** → Claude should tell you in the docstring
- **Does it match our architecture?** → Compare to `architecture.md`
- **What does it output?** → Run it and check the output matches the acceptance criteria

If you're unsure, ask: *"Explain what this code does in plain English, as if I'm a non-programmer project manager."*

### When Claude Gives You Multiple Options

Claude sometimes offers "Option A or Option B." Always pick based on:
1. Which option matches our `model_config.yaml` and architecture doc
2. Which option is simpler (fewer dependencies)
3. When in doubt → ask Claude: *"Which option better matches our project architecture in architecture.md?"*

---

## Error Handling

When code throws an error, use this exact process:

**Step 1 — Copy the full error:**
```
Our script threw this error during Day [X] execution:

--- SCRIPT: [filename] ---
--- ERROR START ---
[PASTE THE COMPLETE ERROR TRACEBACK — not just the last line]
--- ERROR END ---

Plain English explanation of what I was trying to do: [e.g. "I was running the training loop for the LSTM model"]

Please:
1. Explain what went wrong in plain English
2. Identify the root cause
3. Give me the complete corrected version of the file — not a patch
```

**Step 2 — Replace, don't patch:**
When Claude gives you corrected code, replace the entire file — don't try to manually patch lines.

**Step 3 — Re-run:**
Run the corrected version. If it still fails, paste the new error. Repeat until it passes.

**Never try to fix errors yourself** by editing the code manually. This creates hard-to-trace hybrid bugs.

---

## What Claude Is Good At in This Project

| Task | Guidance |
|------|---------|
| Writing complete Python classes | Provide the class name, inputs, outputs, and constraints |
| Writing Docker + docker-compose configs | Tell it the services, ports, and volume mounts |
| Writing Logstash pipeline configs | Describe the input format and output destination |
| Writing React components | Specify layout, props, data shape, and accessibility requirements |
| Writing pytest test cases | Give it the test ID, what to test, and the expected result |
| Explaining error tracebacks | Paste the full traceback |
| Writing markdown documentation | Give it the structure and what each section should cover |
| Generating mock JSON data | Describe the data shape and the scenario (e.g. CUST-18656) |
| Checking code for WCAG compliance | Paste the component and ask for WCAG 2.2 AA review |

---

## What to Watch Out For

### Placeholder Code
Claude sometimes writes `# TODO: implement this` or `pass` stubs. This is not acceptable.

**How to catch it:** Read through the response for any `TODO`, `pass`, `raise NotImplementedError`, or `...` that isn't intentional.

**How to fix it:** Say: *"This code contains placeholder stubs. Please complete all functions with full operational implementations — no TODOs or stubs."*

### Hallucinated Library Versions
Claude may suggest a function or parameter that doesn't exist in the version you're using.

**How to catch it:** If the code fails with `AttributeError` or `ImportError`, paste the error back.

**How to fix it:** Say: *"We are using TensorFlow 2.x / PyTorch 2.x / Elasticsearch 8.x. Please rewrite using only features available in these exact versions."*

### Over-Complex Solutions
Claude sometimes offers overly engineered solutions with unnecessary abstractions.

**How to fix it:** Say: *"This is a 12-week prototype, not a production system. Simplify this to the most straightforward implementation that meets the acceptance criteria."*

### Wrong File Path
Claude may assume a different project structure.

**Always remind Claude:** *"Our project follows the directory structure in architecture.md. All Python source files go in src/. All test files go in tests/."*

---

## Day-by-Day Claude Usage Guide

### Days 1–2: Infrastructure & Data
Claude's job is to write config files and data processing scripts. These are deterministic — the output should be exactly what you specify. If it writes extra features you didn't ask for, ask it to remove them.

**Key check:** Does the feature engineering script produce exactly 12 features? Run `print(features.shape)` — should be `(n_sequences, 5, 12)`.

### Days 3–5: LSTM Model
Claude will write PyTorch/TensorFlow code. You don't need to understand the math — you need to confirm:
- The model architecture matches `architecture.md` Section 3.3
- The training loop runs for 10 epochs
- The final accuracy is ≥ 98.55% and FPR ≤ 0.50%

**Key check:** After training, run `print(final_metrics)` — must show accuracy ≥ 98.55%.

### Day 6: Docker
Claude will write Dockerfiles and docker-compose. You need to:
1. Have Docker Desktop installed and running
2. Run `docker-compose up` in the project root
3. Verify all containers start: `docker ps` should show 5+ running containers

**Key check:** `curl http://localhost:8501/v1/models/lstm` → should return model status JSON.

### Days 7–8: SIEM & Hybrid Scorer
Claude will write Python rule engine code and the hybrid scorer. You need to run the CUST-18656 test scenario and confirm the output matches the dashboard wireframe in Section 5.4 of the project report.

**Key check:** The hybrid scorer must return `threat_score=0.74` and `playbook_triggered=True` for the CUST-18656 scenario.

### Days 10–11: Dashboard
Claude will write React components. You need to:
1. Run `npm install` then `npm start` to see the dashboard locally
2. Verify all 4 panels are visible
3. Check the CUST-18656 data populates correctly
4. Deploy to Vercel: `vercel --prod`

**Key check:** Open the Vercel URL in a browser. Run Lighthouse → Accessibility score must be ≥ 90.

### Day 12: Acceptance Tests
Claude will write pytest tests. You need to run them and confirm all 10 pass.

```bash
pytest tests/test_acceptance.py -v
```

Expected output:
```
PASSED tests/test_acceptance.py::test_AT1_ingestion_latency
PASSED tests/test_acceptance.py::test_AT2_lstm_fraud_flag
PASSED tests/test_acceptance.py::test_AT3_lstm_clean_pass
PASSED tests/test_acceptance.py::test_AT4_siem_alert_latency
PASSED tests/test_acceptance.py::test_AT5_playbook_containment
PASSED tests/test_acceptance.py::test_AT6_analyst_close_audit
PASSED tests/test_acceptance.py::test_AT7_compliance_report
PASSED tests/test_acceptance.py::test_AT8_keyboard_navigation
PASSED tests/test_acceptance.py::test_AT9_rbac_denial
PASSED tests/test_acceptance.py::test_AT10_retraining_pipeline
10 passed in Xs
```

### Days 13–14: Documentation
Claude will write markdown documentation. Read through each doc and check:
- Does it accurately describe what was actually built?
- Does it reference the correct file paths from the actual repo?
- Does the compliance mapping cover all three frameworks?

---

## Useful Claude Prompts to Keep Handy

**Check code against project standards:**
```
Review this code against our project standards:
- PEP 8 compliance (would pass flake8)
- Full type annotations on all functions
- Docstrings on all classes and methods
- Exception handlers on all I/O operations
- No hardcoded credentials or file paths
- No raw PII in any output

[PASTE CODE HERE]

List any violations and provide the corrected version.
```

**Generate mock test data:**
```
Generate a mock JSON array of 6 banking transactions for the CUST-18656 scenario.
Customer is in Darwin, NT, Australia.
Transactions happen between 11:27 and 11:37 AEST.
Amounts: $256.74, $71.28, $61.59, $69.46, $59.53, $146.60
Channels alternating between Card and Online Banking
MCC codes: 5732 (electronics) and 5812 (restaurants)
All SIEM rules should PASS individually.
LSTM anomaly score: 0.74
Include fields: transaction_id, customer_id, amount, channel, merchant_name, mcc_code, timestamp, location, siem_rules, lstm_score, threat_score
```

**Generate the compliance report section:**
```
Write the APRA CPS 234 compliance mapping section for compliance/control_mapping.md.
For each CPS 234 paragraph number, map it to the specific system control in Meridian Sentinel.
System controls available: TLS 1.3, AES-256 at rest, RBAC (6 roles), session timeout 15 min, immutable audit trail, automated playbooks, PII obfuscation at ingestion, LSTM anomaly detection, SIEM correlation engine, 10 acceptance test cases.
Format as a markdown table with columns: CPS 234 Paragraph | Requirement Summary | Meridian Sentinel Control | Evidence Location.
```

**Review for accessibility:**
```
Review this React component for WCAG 2.2 Level AA compliance.
Check:
1. All interactive elements have aria-label attributes
2. Colour contrast meets 4.5:1 minimum (background #0f172a, text #f1f5f9)
3. All elements are keyboard navigable (tabIndex, onKeyDown handlers)
4. Dynamic content updates use aria-live="polite" 
5. All images have alt text
6. Focus rings are visible on all interactive elements
7. No information conveyed by colour alone

[PASTE COMPONENT CODE HERE]

List all violations and provide the corrected component.
```

---

## When You're Stuck

If you're completely stuck on something, describe the situation to Claude like this:

```
I'm on Day [X] of the Meridian Sentinel project. I'm trying to [DESCRIBE WHAT YOU'RE DOING].

Here's what I've done so far:
[LIST STEPS]

Here's what I expected to happen:
[EXPECTED OUTCOME]

Here's what actually happened:
[ACTUAL OUTCOME — include any error messages]

What should I do next?
```

Claude will give you a clear next step. Follow it exactly.

---

## End-of-Day Checklist

Before ending each working session, confirm with Claude:

```
Before I finish for the day, can you confirm:
1. What files were created or modified today?
2. What should I commit to dev?
3. Which acceptance tests are now passing?
4. What is the first task for tomorrow (Day [X+1])?
5. Are there any open issues I need to be aware of?
```

This ensures continuity between sessions even though Claude has no memory between conversations.

---

## File to Give to Claude at the Start of Every New Conversation

To quickly onboard Claude at the start of each new session, copy-paste this block:

```
PROJECT ONBOARDING — Meridian Sentinel

I'm building the Meridian Sentinel cybersecurity prototype for Meridian Financial Services (ITW601 university project). Quick context:

- Hybrid LSTM + Elastic SIEM real-time fraud detection system
- LSTM: 128→64 stacked units, 30% dropout, trained on PaySim (6.3M transactions)
- Target: 98.55% accuracy, 0.50% FPR ✅ (already achieved in prototype)
- SIEM: Elasticsearch 8.x + Kibana + Logstash + Filebeat (Docker)
- Dashboard: React + TypeScript + Tailwind, dark theme, WCAG 2.2 AA
- Compliance: APRA CPS 234, PCI DSS v4.0, Australian Privacy Act 1988
- Deployment: Google Colab (training), Docker (local), Vercel (dashboard)

I am the PM/Architect. You are the Senior Software Engineer.
Write complete, operational code only — no stubs, no TODOs.
All code: PEP 8, type annotations, docstrings, exception handlers.
No credentials in source code. PII SHA-256 hashed at ingestion.

Today is Day [X]. Task: [DESCRIBE TASK]
```
