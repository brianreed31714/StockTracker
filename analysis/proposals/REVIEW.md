# StockTracker Proposals — 2026-09-28

Paper-trading model improvement proposals. Human approval is required before implementation/deployment.

## P-STOCK-20260928-01 — Add forward-outcome cohorts for threshold and confirmation events

- **Status:** PENDING
- **Type:** CODE
- **Target:** Decision-funnel SHADOW instrumentation and daily review export
- **Current:** The funnel identifies raw crossings, confirmation waits, cap blocks, and submissions, but does not provide forward returns or adverse/favorable excursion for each event.
- **Proposed:** For every raw threshold crossing, persist symbol, side, score, threshold distance, position state, confirmation count, final gate disposition, and 5/15/30/60-minute forward return plus MFE/MAE. Report cohorts by symbol and side only after at least 12 eligible observations; make no automatic threshold changes.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Additional storage and delayed-price joins; missing future bars must be marked unavailable rather than imputed.
- **Evidence:**
  - Only 13 raw crossings occurred today.
  - Nine funnel events were awaiting confirmation and two were blocked by MAX_OPEN_POSITIONS.
  - Only 3 realized exits are available, below the minimum calibration sample.

**Approve in ChatGPT:**

`Approve P-STOCK-20260928-01`

**Decline in ChatGPT:**

`Decline P-STOCK-20260928-01`

---

## P-STOCK-20260928-02 — Shadow-audit geo headline deduplication and marginal score impact

- **Status:** PENDING
- **Type:** CODE
- **Target:** Geo-feed aggregation and score-attribution logging
- **Current:** The feed reports 220 active events and includes several closely related or duplicated Hormuz headlines. Production geo adjustments reached an XOM daily average of +3.415, but no deduplication comparison or forward-outcome attribution is shown.
- **Proposed:** Create a SHADOW fingerprint based on normalized title, canonical source, event time, category, and direction. Log raw versus deduplicated event counts and calculate a non-applied deduplicated geo adjustment alongside the current adjustment. Preserve the active production adjustment until sufficient outcome evidence exists.
- **Confidence:** MEDIUM
- **Recommended mode:** SHADOW
- **Risk:** Over-aggressive fingerprinting could merge distinct updates; keep the deduplicated value observational and retain raw records.
- **Evidence:**
  - Multiple CNBC/cnbc.com entries share the same Hormuz subject and timestamp.
  - XOM received the largest average geo adjustment but placed no order.
  - No geo-component forward outcomes were supplied.

**Approve in ChatGPT:**

`Approve P-STOCK-20260928-02`

**Decline in ChatGPT:**

`Decline P-STOCK-20260928-02`

---

## P-STOCK-20260928-03 — Restore and validate XLF/FAS/FAZ SHADOW snapshot collection

- **Status:** PENDING
- **Type:** CODE+CONFIG
- **Target:** Financial-leverage SHADOW market-data collector and health telemetry
- **Current:** The feature is enabled, but snapshot, signal, and outcome tables all contain zero rows; XLF/FAS/FAZ premarket gaps are null and the dashboard reports FINANCIAL_SNAPSHOT_UNAVAILABLE.
- **Proposed:** Add startup and per-refresh validation for XLF, FAS, and FAZ quotes/bars on the configured IEX feed; record explicit failure categories such as unsupported symbol, empty bars, stale timestamp, or join failure. Backfill nothing. Resume only SHADOW candidate and 5/15/30/60-minute outcome logging when all required inputs pass freshness checks.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Feed coverage may not support every symbol consistently; the feature must fail closed to candidate NONE and must not affect paper orders.
- **Evidence:**
  - Financial-leverage snapshot_rows, signal_rows, and outcome_rows are all zero.
  - The configured outcome horizons already exist but generated no evidence.
  - Premarket gaps for XLF, FAS, and FAZ are null.

**Approve in ChatGPT:**

`Approve P-STOCK-20260928-03`

**Decline in ChatGPT:**

`Decline P-STOCK-20260928-03`

---

## P-STOCK-20260928-04 — Instrument premarket bias application and expiry

- **Status:** PENDING
- **Type:** CODE
- **Target:** Premarket-context audit trail
- **Current:** Five bearish snapshots and negative SPY/QQQ gaps were captured, but the dashboard later showed a zero premarket adjustment. The evidence does not connect each refresh to the first-hour decisions or subsequent returns.
- **Proposed:** For each configured premarket refresh, log gaps, bias score, geo contribution, missing-source flags, and the exact adjustment scheduled. During the first 60 regular-session minutes, log applied adjustment, age, expiry reason, counterfactual score without the adjustment, and 15/30/60-minute forward returns. Require at least 12 complete sessions or eligible event cohorts before calibration.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** More logging around the market open; timestamps and session calendars must be normalized to avoid false expiry diagnoses.
- **Evidence:**
  - All 5 snapshots were BEARISH with latest bias score 25.0.
  - Latest gaps were SPY -0.342% and QQQ -0.523%.
  - Dashboard signal records showed premarket_adjustment 0.0.
  - Social status was UNAVAILABLE and must remain explicitly missing.

**Approve in ChatGPT:**

`Approve P-STOCK-20260928-04`

**Decline in ChatGPT:**

`Decline P-STOCK-20260928-04`

---

## P-STOCK-20260928-05 — Add regime and VIX outcome-coverage reporting without gating trades

- **Status:** PENDING
- **Type:** CODE
- **Target:** Market-regime SHADOW daily report
- **Current:** All 79 regime snapshots were RISK_ON and all 11 linked decisions were ALLOW_EQUITY. VIX contributions are logged but lack state-conditioned outcome coverage.
- **Proposed:** Retain the current non-enforcing regime behavior and add state duration, transition counts, stale-state flags, continuous VIX level/change, linked decision outcomes, and sample counts by regime state and symbol. Suppress comparative performance claims until each compared state has at least 12 eligible observations.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Single-state periods may produce long-running incomplete comparisons; reports must label unsupported states rather than extrapolate.
- **Evidence:**
  - Regime state coverage was exclusively RISK_ON.
  - Only 11 regime-linked decisions were recorded.
  - Average VIX score adjustments were very small and have no supplied causal outcome evidence.

**Approve in ChatGPT:**

`Approve P-STOCK-20260928-05`

**Decline in ChatGPT:**

`Decline P-STOCK-20260928-05`

---

## Quick command

`Review today's StockTracker proposals`
