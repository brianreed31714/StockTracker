# StockTracker Proposals — 2026-10-05

Paper-trading model improvement proposals. Human approval is required before implementation/deployment.

## P-STOCK-20261005-01 — Emit a complete decision-funnel row for every scored decision

- **Status:** PENDING
- **Type:** CODE
- **Target:** decision_funnel and order_attempt instrumentation
- **Current:** The system published 1,116 decisions but zero decision-funnel and order-attempt rows; gate counts are empty. At least one AMZN score was below the configured sell threshold, yet raw crossing and position eligibility cannot be audited.
- **Proposed:** For every decision_event_id, emit a funnel row containing symbol, score, side-specific raw threshold crossing, position eligibility, confirmation count, portfolio-cap result, daily-loss result, final disposition, and explicit gate reason. Emit an order-attempt row only when submission is actually requested, including requested quantity/notional, accepted status, order ID, or failure reason. Add a daily reconciliation check between decisions, crossings, attempts, accepted orders, orders, and fills. Do not alter thresholds or controls.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Low implementation risk if logging is asynchronous; validate that instrumentation cannot submit orders or affect decision timing.
- **Evidence:**
  - 1,116 decision rows versus zero decision_funnel rows
  - order_gate_counts is empty
  - AMZN minimum score was 24.685 versus sell threshold 30
  - No requested notional, accepted-order, or gate evidence exists

**Approve in ChatGPT:**

`Approve P-STOCK-20261005-01`

**Decline in ChatGPT:**

`Decline P-STOCK-20261005-01`

---

## P-STOCK-20261005-02 — Join regime SHADOW states to decisions and forward outcomes

- **Status:** PENDING
- **Type:** CODE
- **Target:** regime_decision_shadow.csv
- **Current:** Twenty-five regime snapshots were all RISK_ON with score 100, but zero regime-decision rows were generated.
- **Proposed:** Create a SHADOW row keyed by decision_event_id containing the contemporaneous regime state/score, original action, hypothetical regime-aware disposition, and 5/15/30/60-minute symbol returns when available. Report state-transition counts and score-component contributions. Keep regime outputs non-blocking and PAPER ONLY.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Forward-return joins can introduce timestamp leakage unless strictly based on data after each decision; enforce event-time cutoffs.
- **Evidence:**
  - market_regime_shadow has 25 rows, all RISK_ON
  - regime_decision_shadow is empty
  - Decision logs contain 1,116 rows but no regime counterfactual attribution

**Approve in ChatGPT:**

`Approve P-STOCK-20261005-02`

**Decline in ChatGPT:**

`Decline P-STOCK-20261005-02`

---

## P-STOCK-20261005-03 — Add explicit premarket collector run-status and gap evidence

- **Status:** PENDING
- **Type:** CODE
- **Target:** premarket_intelligence collector and daily evidence export
- **Current:** Premarket is enabled with five refresh offsets, but the table is empty and no latest gap, bias, geo status, or run reason is available. Social source is explicitly unavailable.
- **Proposed:** At each configured offset, emit either a premarket snapshot or a status row with scheduled time, process start time, market calendar status, provider status, per-symbol previous close and premarket price, gap percentage, computed bias, geo status, and skip/error reason. Record social_status=UNAVAILABLE without fabricating sentiment. Keep any context adjustment in SHADOW until at least 12 eligible sessions are collected.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Provider limitations may leave gaps; status rows must distinguish missing quotes from true zero gaps.
- **Evidence:**
  - premarket_intelligence has zero rows
  - premarket_enabled is true
  - premarket refresh offsets are 30,20,10,5,1 minutes
  - premarket_social_source is UNAVAILABLE

**Approve in ChatGPT:**

`Approve P-STOCK-20261005-03`

**Decline in ChatGPT:**

`Decline P-STOCK-20261005-03`

---

## P-STOCK-20261005-04 — Restore auditable XLF/FAS/FAZ SHADOW snapshots and outcomes

- **Status:** PENDING
- **Type:** CODE
- **Target:** financial_leverage_shadow, financial_leverage_signals, and financial_leverage_outcomes
- **Current:** Financial-leverage SHADOW is enabled, but all related tables are empty and the dashboard reports FINANCIAL_SNAPSHOT_UNAVAILABLE.
- **Proposed:** Emit one status or snapshot row per evaluation containing XLF, FAS, and FAZ quote timestamps, freshness, provider, score components, regime state, candidate or NONE, and failure reason. For eligible signals, record hypothetical entry price and strictly forward 5/15/30/60-minute outcomes. Do not create paper orders or change the score threshold until each candidate class has at least 12 resolved outcomes.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Leveraged and inverse ETF data can be stale or asynchronous; freshness checks are required before evaluating signals.
- **Evidence:**
  - Zero financial-leverage snapshot, signal, and outcome rows
  - Latest dashboard candidate is NONE with FINANCIAL_SNAPSHOT_UNAVAILABLE
  - Configured outcome horizons are 5,15,30,60 minutes

**Approve in ChatGPT:**

`Approve P-STOCK-20261005-04`

**Decline in ChatGPT:**

`Decline P-STOCK-20261005-04`

---

## P-STOCK-20261005-05 — Instrument geo-feed deduplication and marginal score attribution

- **Status:** PENDING
- **Type:** CODE
- **Target:** geo feed normalization and decision evidence
- **Current:** The feed had 410 active events and materially adjusted XOM and GLD scores, while top events included duplicate or near-duplicate reporting of the same Hormuz export story. No forward-outcome attribution exists.
- **Proposed:** Assign normalized event-cluster IDs using canonical URL, title similarity, event time, and underlying incident. Log raw adjustment, deduplicated adjustment, capped adjustment, contributing cluster count, and score/action counterfactual with geo set to zero. Collect forward returns in SHADOW; do not change the current adjustment cap from this one-day sample.
- **Confidence:** MEDIUM
- **Recommended mode:** SHADOW
- **Risk:** Over-aggressive clustering could merge genuinely independent reports; preserve raw events and cluster confidence for audit.
- **Evidence:**
  - XOM average geo adjustment was +2.561 and GLD was +0.640
  - Latest feed adjustment was +2.92 with 410 active events
  - Two top headlines describe the same 60% export-drop story at the same publication time
  - No orders or realized outcomes permit causal assessment

**Approve in ChatGPT:**

`Approve P-STOCK-20261005-05`

**Decline in ChatGPT:**

`Decline P-STOCK-20261005-05`

---

## P-STOCK-20261005-06 — Add ZPTA prediction-independence and shadow-trade diagnostics

- **Status:** PENDING
- **Type:** CODE
- **Target:** ZPTA model evaluation and zpta_shadow_trades.csv
- **Current:** ZPTA resolved 128 predictions without missing returns, but model families share identical average returns within horizons and no shadow trades or exit reasons were emitted.
- **Proposed:** Report unique observation count, overlapping-window count, prediction correlation across model families, class balance, and confidence-bucket outcomes. Emit a diagnostic reason whenever a prediction does not become a shadow trade, such as score below 68, stale delayed data, no new bar, liquidity block, or duplicate signal. If a shadow trade is opened, record hypothetical notional capped at $150, entry/exit timestamps, exit reason, and paper-only P/L. Make no calibration change until at least 12 resolved, non-overlapping examples per model/horizon are available.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Non-overlap filtering will reduce sample counts but will produce more defensible evaluation; shadow trades must remain isolated from the portfolio engine.
- **Evidence:**
  - 12 observations, 156 predictions, and 128 resolved predictions
  - 5-minute summaries have 12 samples; 15- and 60-minute summaries have 10
  - Average returns are identical across model families within each horizon
  - Zero zpta_shadow_trades and empty exit-reason counts
  - Latest provider was yahoo_delayed and status was NO_NEW_BAR

**Approve in ChatGPT:**

`Approve P-STOCK-20261005-06`

**Decline in ChatGPT:**

`Decline P-STOCK-20261005-06`

---

## Quick command

`Review today's StockTracker proposals`
