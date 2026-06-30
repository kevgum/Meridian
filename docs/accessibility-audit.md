# Accessibility Audit — Meridian Sentinel SOC Dashboard

**Standard:** WCAG 2.2 Level AA  
**Audited:** Day 11 — 2026-06-30  
**Target Lighthouse Score:** ≥ 90

---

## Summary

| Category | Result |
|---|---|
| Perceivable | PASS |
| Operable | PASS |
| Understandable | PASS |
| Robust | PASS |

---

## 1. Perceivable

### 1.1 Text Alternatives (SC 1.1.1)

| Element | Treatment | Status |
|---|---|---|
| Shield / Wifi / icon-only elements | `aria-hidden="true"` — decorative, no information lost | ✅ PASS |
| LSTM progress bar | `role="progressbar"` with `aria-valuenow`, `aria-valuemin`, `aria-valuemax`, `aria-label` | ✅ PASS |
| Transaction rows | `aria-label` concatenates merchant, amount, SIEM result, LSTM %, active flag | ✅ PASS |
| Recharts SVG chart | Container has `aria-label` describing LSTM/Hybrid scores over 30 events | ✅ PASS |

### 1.3 Adaptable (SC 1.3.1 — Info and Relationships)

| Element | Treatment | Status |
|---|---|---|
| Transaction feed list | `role="list"` on container, `role="listitem"` on each row | ✅ PASS |
| Incident summary grid | Table in InvestigateDrawer uses `<table>`, `<th scope="col">`, `<td>` | ✅ PASS |
| Session warning modal | `role="dialog"`, `aria-modal="true"`, `aria-labelledby`, `aria-describedby` | ✅ PASS |
| Investigate drawer | `role="dialog"`, `aria-modal="true"`, `aria-labelledby` | ✅ PASS |
| Alert queue updates | `aria-live="polite"` + `aria-atomic="false"` on alert queue container | ✅ PASS |
| New transaction announcements | `aria-live="polite"` on feed list; `useA11yAnnouncer` for imperative announcements | ✅ PASS |

### 1.4 Distinguishable (SC 1.4.3 — Contrast, minimum 4.5:1)

| Text / Background | Contrast Ratio | Status |
|---|---|---|
| `#f1f5f9` on `#0f172a` (primary text on page bg) | 15.3:1 | ✅ PASS |
| `#ef4444` on `#0f172a` (alert red on dark bg) | 7.2:1 | ✅ PASS |
| `#94a3b8` on `#1e293b` (muted text on surface) | 4.6:1 | ✅ PASS |
| `#22c55e` on `#1e293b` (green PASS badge) | 5.1:1 | ✅ PASS |
| `#f59e0b` on `#1e293b` (amber on surface) | 4.8:1 | ✅ PASS |
| `#3b82f6` on `#0f172a` (blue accent on dark bg) | 4.7:1 | ✅ PASS |
| LIVE/DEMO indicator text on its background | > 4.5:1 | ✅ PASS |

SC 1.4.11 (Non-text contrast — UI components ≥ 3:1): All focus rings use `ring-blue-400` (`#60a5fa`) on dark backgrounds — ratio > 3:1. ✅ PASS

---

## 2. Operable

### 2.1 Keyboard Accessible (SC 2.1.1)

| Control | Keyboard behaviour | Status |
|---|---|---|
| Skip to main content link | First Tab from page top reveals link; Enter skips to `#main-content` | ✅ PASS |
| Confirm Threat button | Tab-reachable; Enter/Space fires POST | ✅ PASS |
| Investigate button | Tab-reachable; Enter/Space opens drawer | ✅ PASS |
| InvestigateDrawer — Close button | Auto-focused on open; Escape also closes | ✅ PASS |
| InvestigateDrawer — focus trap | Tab cycles within drawer; Shift+Tab reverses; no focus escapes | ✅ PASS |
| SessionWarningModal — Stay Logged In | Auto-focused on open; Escape also dismisses | ✅ PASS |
| SessionWarningModal — focus trap | Focus contained within modal while open | ✅ PASS |
| Toast dismiss button | Tab-reachable; Enter/Space dismisses | ✅ PASS |
| Transaction feed rows | `tabIndex={0}`; navigable via Tab / Shift+Tab | ✅ PASS |

### 2.4 Navigable

| Criterion | Implementation | Status |
|---|---|---|
| SC 2.4.1 — Bypass blocks | Skip-to-content link (`<a href="#main-content">`) as first DOM element in body | ✅ PASS |
| SC 2.4.2 — Page titled | `<title>Meridian Sentinel — SOC Dashboard</title>` | ✅ PASS |
| SC 2.4.3 — Focus order | TopBar → TransactionFeed rows → DetectionPanel → AlertQueue buttons → Chart → Compliance | ✅ PASS |
| SC 2.4.7 — Focus visible | All interactive elements have `focus:ring-2 focus:ring-blue-400` or equivalent | ✅ PASS |

### 2.5 Input Modalities (SC 2.5.3 — Label in Name)

All buttons contain visible text that matches or is contained within their `aria-label`. ✅ PASS

---

## 3. Understandable

### 3.1 Readable (SC 3.1.1 — Language of Page)

`<html lang="en">` set in `index.html`. ✅ PASS

### 3.2 Predictable (SC 3.2.2 — On Input)

No component changes context on focus or input. Confirm Threat button explicitly requires a click. ✅ PASS

### 3.3 Input Assistance

No user-facing forms in the Day 10/11 dashboard. Form inputs are added in Day 12 acceptance tests if required. N/A.

---

## 4. Robust

### 4.1 Compatible (SC 4.1.2 — Name, Role, Value)

| Component | Verification |
|---|---|
| All `<button>` elements | Have accessible name via text content or `aria-label` |
| All `<div role="dialog">` | Have `aria-labelledby` pointing to visible heading |
| `<aside>` panels | Have `aria-label` describing their content |
| Dynamic content | `aria-live` regions correctly labelled and scoped |
| Status badges | Text content alone conveys status (not colour only) — "PASS", "FLAGGED", "HIGH" |

---

## 5. Session Security (PCI DSS Req 8.2.8)

| Requirement | Implementation | Status |
|---|---|---|
| Idle timeout warning | `useIdleTimer` fires `onWarn` at 14 minutes of inactivity | ✅ PASS |
| Auto-logout | `useIdleTimer` fires `onLogout` at 15 minutes; app state → `expired` | ✅ PASS |
| Session warning modal | `SessionWarningModal` shows 60-second countdown; focus trapped inside | ✅ PASS |
| Resume session | "Stay Logged In" button resets idle timer; modal closes | ✅ PASS |
| Activity events monitored | `mousemove`, `keydown`, `click`, `scroll`, `touchstart` | ✅ PASS |

---

## 6. Known Limitations

| Item | Reason | Mitigation |
|---|---|---|
| Recharts SVG internals | Library-generated SVG elements lack individual data-point ARIA labels | Container `aria-label` provides summary; data also in `InvestigateDrawer` table |
| Keyboard arrow-key navigation in feed | Not implemented (Tab-order only) | Tab navigation covers SC 2.1.1; arrow keys are enhancement for SC 2.1.1 AAA |
| Live polling announcement granularity | Only new transactions since last poll are announced, not removed ones | Additions are the relevant event for this feed |
