# StockTracker Proposals — 2026-09-25

Paper-trading model improvement proposals. Human approval is required before implementation/deployment.

## P-STOCK-20260925-01 — Add a decision-to-order funnel with explicit gate reasons

- **Status:** PENDING
- **Type:** CODE
- **Target:** Decision audit records and paper-order submission pipeline
- **Current:** Decision rows contain final actions, but the evidence does not expose raw threshold-cross events, confirmation counters, position eligibility, cap checks, market-session checks, or reasons why a BUY did not create an order.
- **Proposed:** For every non-HOLD candidate and every raw score crossing, log symbol, side, score, threshold, consecutive-confirmation count, current position state, projected paper exposure, open-position count, market-session state, final disposition, and a single enumerated gate reason. Record paper-order attempt and acceptance identifiers separately. Do not alter thresholds or execution behavior.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Low operational risk; added logging volume and schema changes must avoid disrupting the one-minute decision loop or exposing unsanitized data.
- **Evidence:**
  - Two TSLA BUY decisions were recorded, but orders and fills were both zero.
  - AMZN, NVDA, and TSLA exceeded the buy threshold by daily maximum, while only TSLA produced BUY actions.
  - NVDA, TSLA, and XOM fell below the sell threshold by daily minimum, while no SELL action was recorded.

**Approve in ChatGPT:**

`Approve P-STOCK-20260925-01`

**Decline in ChatGPT:**

`Decline P-STOCK-20260925-01`

---

## P-STOCK-20260925-02 — Enforce and audit paper portfolio-cap invariants before every BUY

- **Status:** PENDING
- **Type:** CODE
- **Target:** Paper portfolio reconciliation and pre-order risk gate
- **Current:** Configured limits are 4 open positions and $10,000 total exposure, while a later dashboard snapshot reports 5 positions and $12,575.46 exposure. The available timestamps cannot determine whether this resulted from legacy state, appreciation, reconciliation drift, or an order-gate defect.
- **Proposed:** Before any paper BUY submission, reconcile paper positions and open orders, calculate projected position count and projected exposure, and reject the order if either configured cap would be exceeded. Emit an invariant-violation event at startup and each cycle when existing state is already above a cap. Keep the dashboard read-only and preserve all existing caps, daily-loss controls, and paper=True.
- **Confidence:** MEDIUM
- **Recommended mode:** PAPER
- **Risk:** Stale or incomplete position reconciliation could conservatively block valid paper entries; the guard must fail closed without liquidating or modifying existing paper positions automatically.
- **Evidence:**
  - Configured max_open_positions is 4 and max_total_exposure is $10,000.
  - The 2026-09-27 dashboard reports 5 positions and $12,575.46 exposure.
  - No same-day order records are available to identify the source of the discrepancy.

**Approve in ChatGPT:**

`Approve P-STOCK-20260925-02`

**Decline in ChatGPT:**

`Decline P-STOCK-20260925-02`

---

## P-STOCK-20260925-03 — Add geo-feed freshness, deduplication, and application diagnostics

- **Status:** PENDING
- **Type:** CODE+CONFIG
- **Target:** Geo-feed ingestion and score-adjustment audit fields
- **Current:** The geo artifact is six days older than the review date, reports a +7.1 adjustment and 249 active events, and includes apparent duplicate stories. Decision aggregates show a 0.0 geo adjustment for every symbol without explaining whether the feed was stale, inapplicable, or unavailable.
- **Proposed:** In SHADOW, canonicalize article URL/domain/title fingerprints, report raw versus deduplicated event counts, record feed age, and attach an enumerated geo-application status to each decision. Add a configurable freshness limit that quarantines stale geo data from scoring while still logging its counterfactual adjustment. Do not activate the supplied +7.1 adjustment or change trading thresholds.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Over-aggressive deduplication could merge genuinely distinct reports; shadow comparison should precede any production scoring effect.
- **Evidence:**
  - Geo generated_at is 2026-09-19T16:41:18.944358+00:00 for a 2026-09-25 review.
  - The feed reports signal 0.7105 and score adjustment 7.1, but all symbols show average geo adjustment 0.0.
  - Multiple top events repeat the same publication time and headline through domain or capitalization variants.

**Approve in ChatGPT:**

`Approve P-STOCK-20260925-03`

**Decline in ChatGPT:**

`Decline P-STOCK-20260925-03`

---

## P-STOCK-20260925-04 — Collect per-symbol threshold and VIX outcome cohorts before calibration

- **Status:** PENDING
- **Type:** RESEARCH
- **Target:** Shadow signal-evaluation dataset
- **Current:** The evidence provides score aggregates and average VIX adjustments but no crossing counts, persistence, forward returns, counterfactual exits, or time-aligned volatility regimes.
- **Proposed:** For each raw buy or sell threshold crossing, record symbol, side, score distance from threshold, confirmation outcome, VIX level and change, geo freshness status, and forward paper returns at 5, 15, and 60 minutes and market close. Keep blocked signals as counterfactual observations. Require at least 12 eligible observations in a defined symbol-side or pooled regime cohort before considering calibration; make no threshold or VIX-weight changes now.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Forward-return research can suffer from missing bars, overlapping observations, and selection bias; results must remain paper-only and should not be treated as causal without adequate cohorts.
- **Evidence:**
  - Only two final BUY actions and zero SELL actions occurred.
  - There are no orders, fills, or realized outcomes.
  - Average VIX adjustments differ by symbol, but the available VIX snapshot is not time-aligned with the review day.

**Approve in ChatGPT:**

`Approve P-STOCK-20260925-04`

**Decline in ChatGPT:**

`Decline P-STOCK-20260925-04`

---

## P-STOCK-20260925-05 — Make review artifacts date-scoped and freshness-aware

- **Status:** PENDING
- **Type:** CODE
- **Target:** Daily review data assembly and dashboard snapshot metadata
- **Current:** The review is dated 2026-09-25, but the dashboard snapshot is from 2026-09-27 and the geo snapshot is from 2026-09-19. These artifacts are presented alongside same-day decisions without an explicit as-of eligibility status.
- **Proposed:** Join artifacts by review date and market timezone, retain source generated_at timestamps, and label each artifact as in-window, stale, or future relative to the review cutoff. Exclude out-of-window dashboard state from same-day portfolio and VIX conclusions while preserving it in a clearly labeled diagnostics section. Keep the dashboard read-only.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Strict date filtering may temporarily reduce report coverage when snapshots are delayed, but it prevents misleading same-day attribution.
- **Evidence:**
  - Review date is 2026-09-25.
  - Dashboard generated_at is 2026-09-27T05:00:08.830944+00:00.
  - Geo generated_at is 2026-09-19T16:41:18.944358+00:00.

**Approve in ChatGPT:**

`Approve P-STOCK-20260925-05`

**Decline in ChatGPT:**

`Decline P-STOCK-20260925-05`

---

## Quick command

`Review today's StockTracker proposals`
