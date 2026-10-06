# StockTracker Proposals — 2026-10-06

Paper-trading model improvement proposals. Human approval is required before implementation/deployment.

## P-STOCK-20261006-01 — Populate decision-funnel lineage for every threshold-relevant decision

- **Status:** PENDING
- **Type:** CODE
- **Target:** decision_funnel.csv and decision-event instrumentation
- **Current:** The decision funnel has zero rows despite 3,150 decisions and at least one observed score above the buy threshold. Gate counts and final dispositions are unavailable.
- **Proposed:** In SHADOW logging, emit a funnel record keyed to decision_event_id whenever a score crosses either raw threshold or has a nonzero confirmation count. Record symbol, side, raw score, threshold, confirmation count/requirement, position state, each evaluated gate, final disposition, and hypothetical requested notional. Do not submit additional orders or alter thresholds.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Low operational risk if writes are asynchronous and failures cannot affect the decision loop. Avoid logging sensitive brokerage data. Preserve paper=True, exposure caps, position caps, trade caps, and daily-loss controls.
- **Evidence:**
  - XOM maximum score was 70.274 versus the 70 buy threshold, yet all XOM decisions were HOLD.
  - decision_funnel and order_attempts both contain zero rows; order_gate_counts is empty.
  - All 3,150 decision rows were analyzed without duplicate event IDs.

**Approve in ChatGPT:**

`Approve P-STOCK-20261006-01`

**Decline in ChatGPT:**

`Decline P-STOCK-20261006-01`

---

## P-STOCK-20261006-02 — Add position-to-fill provenance and daily reconciliation fields

- **Status:** PENDING
- **Type:** CODE
- **Target:** dashboard position snapshot and evidence publisher
- **Current:** The dashboard shows three open positions, but same-day orders and fills are empty, leaving their opening date and fill lineage unknown in the review evidence.
- **Proposed:** Add read-only fields for position_origin_date, opening_order_id, opening_fill_id, carried_from_prior_day, and reconciled_quantity. Publish a reconciliation summary that separately totals requested notional, accepted orders, fills, realized P/L, and dashboard-only positions. Flag mismatches without changing positions or submitting orders.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Low if implemented as read-only instrumentation. Brokerage/order identifiers should remain sanitized. Dashboard behavior must remain read-only.
- **Evidence:**
  - Dashboard snapshot reports AAPL, SPY, and XOM positions with $7,608.47 exposure.
  - Same-day orders, fills, and realized tables each contain zero rows.
  - Dashboard unrealized P/L cannot be treated as realized P/L or same-day execution evidence.

**Approve in ChatGPT:**

`Approve P-STOCK-20261006-02`

**Decline in ChatGPT:**

`Decline P-STOCK-20261006-02`

---

## P-STOCK-20261006-03 — Link regime snapshots to contemporaneous decisions and forward outcomes

- **Status:** PENDING
- **Type:** CODE
- **Target:** regime_decision_shadow.csv
- **Current:** Seventy market-regime snapshots were recorded, all RISK_ON at score 100, but no regime-decision linkage rows were published.
- **Proposed:** For each decision, write a SHADOW linkage to the latest nonfuture regime snapshot, including snapshot age, state, score, hypothetical regime-adjusted action, unchanged baseline action, and forward returns at fixed horizons when available. Do not let the regime shadow alter paper orders until multiple states and adequate outcome samples exist.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Low instrumentation risk; timestamp joins must prohibit look-ahead. A single-state day could otherwise produce misleading apparent performance.
- **Evidence:**
  - market_regime_shadow has 70 rows spanning 14:10–19:57 UTC.
  - All 70 observations are RISK_ON with score 100.
  - regime_decision_shadow has zero rows, preventing assessment of incremental contribution.

**Approve in ChatGPT:**

`Approve P-STOCK-20261006-03`

**Decline in ChatGPT:**

`Decline P-STOCK-20261006-03`

---

## P-STOCK-20261006-04 — Emit financial-leverage availability diagnostics and XLF/FAS/FAZ outcomes

- **Status:** PENDING
- **Type:** CODE+CONFIG
- **Target:** financial_leverage_shadow, financial_leverage_signals, and financial_leverage_outcomes publishers
- **Current:** Financial-leverage SHADOW is enabled, but all related tables are empty and the dashboard only reports FINANCIAL_SNAPSHOT_UNAVAILABLE.
- **Proposed:** Keep the feature SHADOW-only. At each scheduled evaluation, log XLF/FAS/FAZ quote/bar availability, provider, bar timestamps, freshness, missing-field reason, candidate score, eligibility result, and rejection reason. When valid signals exist, record non-trading forward returns at the configured 5/15/30/60-minute horizons.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Moderate data-volume and provider-rate risk. No leveraged ETF orders should be created, and the configured minimum score must remain unchanged.
- **Evidence:**
  - financial_leverage_shadow, financial_leverage_signals, and financial_leverage_outcomes each have zero rows.
  - The latest dashboard candidate is NONE with FINANCIAL_SNAPSHOT_UNAVAILABLE.
  - No XLF/FAS/FAZ signal or forward-outcome evidence exists for calibration.

**Approve in ChatGPT:**

`Approve P-STOCK-20261006-04`

**Decline in ChatGPT:**

`Decline P-STOCK-20261006-04`

---

## P-STOCK-20261006-05 — Add premarket schedule heartbeats, gap provenance, and bias-outcome logging

- **Status:** PENDING
- **Type:** CODE
- **Target:** premarket_intelligence.csv
- **Current:** Premarket collection is enabled for five refresh offsets, but the table contains zero rows and all latest gap/bias fields are absent.
- **Proposed:** At every configured offset, emit a SHADOW heartbeat even on failure. Record expected and actual run time, symbol-level prior close and premarket price timestamps, gap percentage, computed bias components, geo status, explicit social_source=UNAVAILABLE, failure reason, and post-open forward returns. Keep premarket adjustment behavior unchanged pending at least 12 valid independent samples.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Low model risk because this only records SHADOW evidence. Timestamp handling must avoid stale quotes and look-ahead; social data must not be fabricated.
- **Evidence:**
  - premarket_enabled is true with offsets 30,20,10,5,1 minutes.
  - premarket_intelligence has zero rows and latest_gaps_pct is empty.
  - All dashboard premarket adjustments are 0.0.
  - Social source is explicitly UNAVAILABLE.

**Approve in ChatGPT:**

`Approve P-STOCK-20261006-05`

**Decline in ChatGPT:**

`Decline P-STOCK-20261006-05`

---

## P-STOCK-20261006-06 — Measure geo deduplication and marginal score contribution without changing weights

- **Status:** PENDING
- **Type:** CODE
- **Target:** geo-feed scoring audit and decision evidence
- **Current:** Geo adjustments materially lift XOM and GLD scores, while the displayed top events contain multiple variants of the same underlying headlines. The evidence does not expose deduplication clusters or counterfactual scores.
- **Proposed:** Log a stable story-cluster ID, canonical URL/title hash, source count, deduplication decision, event-level contribution, total capped contribution, and counterfactual score_without_geo for each affected decision. Record whether geo alone changed a raw threshold-crossing state and attach fixed-horizon forward returns. Do not change the geo cap or weight.
- **Confidence:** MEDIUM
- **Recommended mode:** SHADOW
- **Risk:** Low trading risk in SHADOW mode; clustering errors may merge distinct updates, so retain raw event IDs and make the audit reversible.
- **Evidence:**
  - XOM average geo adjustment was +3.64 and GLD was +0.91; other symbols averaged zero.
  - The top-event list repeats WSJ and TradeWinds stories across source/title variants.
  - XOM's maximum total score exceeded the buy threshold, but the marginal role of geo at that timestamp is not supplied.
  - Geo log tail had zero errors and 25 warnings, but warning categories are not summarized.

**Approve in ChatGPT:**

`Approve P-STOCK-20261006-06`

**Decline in ChatGPT:**

`Decline P-STOCK-20261006-06`

---

## Quick command

`Review today's StockTracker proposals`
