# StockTracker Proposals — 2026-10-08

Paper-trading model improvement proposals. Human approval is required before implementation/deployment.

## P-STOCK-20261008-01 — Restore and verify premarket and XLF/FAS/FAZ SHADOW pipelines

- **Status:** APPROVED (user authorization 2026-10-09; implementation/deployment pending)
- **Type:** CODE
- **Target:** premarket_intelligence and financial_leverage SHADOW publishers
- **Current:** Both features are enabled, but premarket intelligence and all three financial-leverage tables published zero rows; the dashboard reports FINANCIAL_SNAPSHOT_UNAVAILABLE.
- **Proposed:** Add startup and scheduled-run diagnostics that emit a SHADOW status row for every expected refresh, including provider, requested symbols, gap fields, source availability, failure class, and retry result. For XLF/FAS/FAZ, publish snapshots even when no candidate qualifies and attach 5/15/30/60-minute forward outcomes. Do not route these signals into paper execution until adequate outcome evidence exists.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Low execution risk because the change is SHADOW-only; operational risk is added log volume and possible provider retries.
- **Evidence:**
  - premarket_intelligence rows: 0 despite premarket_enabled=true.
  - financial_leverage snapshot, signal, and outcome rows: 0 despite financial_leverage_shadow_enabled=true.
  - Dashboard reason: FINANCIAL_SNAPSHOT_UNAVAILABLE.
  - Social source is explicitly UNAVAILABLE and must remain represented as unavailable rather than inferred.

**Approve in ChatGPT:**

`Approve P-STOCK-20261008-01`

**Decline in ChatGPT:**

`Decline P-STOCK-20261008-01`

---

## P-STOCK-20261008-02 — Add symbol-level missed-opportunity and confirmation outcome records

- **Status:** APPROVED (user authorization 2026-10-09; implementation/deployment pending)
- **Type:** CODE
- **Target:** decision_funnel and forward-outcome instrumentation
- **Current:** Five events were blocked awaiting confirmation, but aggregate evidence does not identify their symbols, exact scores, confirmation sequences, position state, or subsequent returns.
- **Proposed:** For every BUY threshold crossing and every near-threshold high-volume event, publish symbol, timestamp, score components, threshold distance, confirmation count, gate reason, position/cap state, volume ratio, short-horizon momentum, and 5/15/30/60-minute forward returns. Include SHADOW counterfactual entries for both immediate entry and current two-confirmation entry. Require at least 12 resolved independent events per symbol/cohort before considering calibration.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** No trading risk in SHADOW mode; counterfactual assumptions must be clearly labeled and include paper slippage rules.
- **Evidence:**
  - NVDA max score 71.235 with no BUY.
  - GLD max score 73.207 with no BUY.
  - QQQ max score 68.711 and late volume ratio 5.157 with positive short momentum.
  - Five funnel events ended AWAITING_CONFIRMATION.
  - No event-level blocked-gate forward outcomes were supplied.

**Approve in ChatGPT:**

`Approve P-STOCK-20261008-02`

**Decline in ChatGPT:**

`Decline P-STOCK-20261008-02`

---

## P-STOCK-20261008-03 — Research ATR-normalized exits beside fixed exits

- **Status:** APPROVED (user authorization 2026-10-09; implementation/deployment pending)
- **Type:** CODE+CONFIG
- **Target:** SHADOW exit evaluator for configured trade symbols
- **Current:** All symbols share fixed 2% stop, 3% take-profit, 1% trailing activation, and 1.25% trailing distance, while no ATR or excursion evidence is logged.
- **Proposed:** Keep current paper execution exits unchanged. Add SHADOW comparators using pre-entry ATR percentage or realized-volatility bands, and record maximum adverse/favorable excursion, time-to-exit, fixed-exit outcome, and volatility-normalized outcome for each paper entry. Segment results by symbol and volatility bucket with a minimum of 12 closed comparisons before any configuration proposal.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Low while SHADOW-only; ATR lookback and bar-source choices could introduce leakage unless fixed at entry time.
- **Evidence:**
  - No ATR, realized-volatility, MAE, or MFE fields were supplied.
  - The universe mixes lower-volatility ETFs and equities with higher-volatility names such as NVDA and TSLA.
  - Only two realized exits occurred today, far below calibration requirements.

**Approve in ChatGPT:**

`Approve P-STOCK-20261008-03`

**Decline in ChatGPT:**

`Decline P-STOCK-20261008-03`

---

## P-STOCK-20261008-04 — Measure and deduplicate geo-feed score contribution

- **Status:** APPROVED (user authorization 2026-10-09; implementation/deployment pending)
- **Type:** CODE
- **Target:** geo event normalization and score-attribution logs
- **Current:** XOM received an average +7.754 geo adjustment, and repeated versions of the same headline appear among top events; no deduplication or with/without-geo forward outcome is published.
- **Proposed:** Cluster geo items by normalized headline, canonical URL, event category, and publication window before aggregation. Log raw item count, unique-event count, capped contribution, and counterfactual score without geo adjustment for each XOM/GLD decision. Keep the live paper score unchanged until at least 12 resolved geo-triggered opportunities have forward outcomes.
- **Confidence:** MEDIUM
- **Recommended mode:** SHADOW
- **Risk:** Incorrect clustering could merge genuinely distinct updates; retain raw events and use SHADOW counterfactuals before changing scoring.
- **Evidence:**
  - XOM average technical score was 50.671 versus average final score 58.226 and average geo adjustment +7.754.
  - GLD average geo adjustment was +1.939.
  - Multiple top events repeat the same Guardian tanker-attack headline.
  - Geo tail contained 14 errors and 34 warnings in 500 lines.

**Approve in ChatGPT:**

`Approve P-STOCK-20261008-04`

**Decline in ChatGPT:**

`Decline P-STOCK-20261008-04`

---

## P-STOCK-20261008-05 — Reconcile funnel counts and expose complete paper order lifecycle

- **Status:** APPROVED (user authorization 2026-10-09; implementation/deployment pending)
- **Type:** CODE
- **Target:** decision_funnel, order_attempt, order, fill, realized, and dashboard audit views
- **Current:** The funnel reports six raw threshold crossings but eight side-classified rows. Lifecycle tables reconcile by count for three accepted attempts/orders/fills, yet dashboard snapshots do not explicitly distinguish requested notional, accepted quantity, filled quantity, and realized status.
- **Proposed:** Define and validate separate counters for unique threshold-crossing episodes, repeated confirmation observations, and final gate events. Add immutable linkage IDs and a read-only audit view showing requested notional, accepted order ID, fill price/quantity, open-versus-closing classification, realized P/L record, and dashboard snapshot timestamp. Fail the daily integrity check on unexplained counter divergence.
- **Confidence:** HIGH
- **Recommended mode:** PAPER
- **Risk:** Low; schema migration and linkage backfills must not alter paper order submission behavior or dashboard write permissions.
- **Evidence:**
  - decision_funnel rows: 8; raw_threshold_crossings: 6; side counts: 5 BUY and 3 SELL.
  - Three attempts were accepted, with three orders and three fills.
  - Only two realized rows exist because the TSLA BUY remained open.
  - Current referential-integrity checks passed, so the remaining issue is metric semantics and presentation.

**Approve in ChatGPT:**

`Approve P-STOCK-20261008-05`

**Decline in ChatGPT:**

`Decline P-STOCK-20261008-05`

---

## P-STOCK-20261008-06 — Diagnose zero ZPTA shadow trades and model-outcome duplication

- **Status:** APPROVED (user authorization 2026-10-09; implementation/deployment pending)
- **Type:** RESEARCH
- **Target:** ZPTA prediction-to-shadow-trade transition
- **Current:** There were 120 predictions and 92 resolved outcomes but zero shadow trades, no exit reasons, and only 7-8 samples per model/horizon. Several model families show identical average returns at each horizon.
- **Proposed:** Trace each prediction through eligibility, entry-score, liquidity/regime, stale-bar, provider, and position-limit gates; publish one terminal reason per prediction. Verify whether identical returns are intentionally shared underlying forward returns or an accidental model-label duplication. Continue collecting SHADOW evidence without tuning the 68 entry score until each evaluated cohort has at least 12 independent resolved cases.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** No execution risk; delayed data may make simulated entry assumptions unreliable, so provider timestamps and staleness must be retained.
- **Evidence:**
  - zpta_shadow_trades rows: 0 and exit-reason counts are empty.
  - Latest status was NO_NEW_BAR using yahoo_delayed data.
  - Latest regime was LIQUIDITY_DANGER.
  - Every reported model/horizon sample count is below 12.
  - Average returns repeat across multiple model families at the same horizon.

**Approve in ChatGPT:**

`Approve P-STOCK-20261008-06`

**Decline in ChatGPT:**

`Decline P-STOCK-20261008-06`

---

## Quick command

`Review today's StockTracker proposals`
