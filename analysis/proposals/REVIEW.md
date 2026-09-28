# StockTracker Proposals — 2026-09-27

Paper-trading model improvement proposals. Human approval is required before implementation/deployment.

## P-STOCK-20260927-01 — Enforce and log existing portfolio caps in the paper order-admission path

- **Status:** PENDING
- **Type:** CODE
- **Target:** Paper portfolio reconciliation and opening-buy admission guard
- **Current:** A dashboard snapshot shows 5 positions and $12,575.46 exposure despite configured caps of 4 positions and $10,000. The cause is not recorded.
- **Proposed:** Before every paper opening buy, reconcile positions and exposure from the paper account, reject the opening order when either existing cap is met or exceeded, and emit a structured cap-breach event containing observed values, configured limits, and order intent. Continue permitting risk-reducing sells. Do not automatically liquidate existing positions from this single snapshot and do not alter any cap values.
- **Confidence:** HIGH
- **Recommended mode:** PAPER
- **Risk:** Low execution risk because this only reinforces existing paper controls, but reconciliation bugs could suppress valid paper entries; retain detailed rejection logging and test with simulated account states.
- **Evidence:**
  - Dashboard open_positions=5 versus max_open_positions=4.
  - Dashboard exposure=$12,575.46 versus max_total_exposure=$10,000.
  - There are no same-day orders or decisions that explain the discrepancy.

**Approve in ChatGPT:**

`Approve P-STOCK-20260927-01`

**Decline in ChatGPT:**

`Decline P-STOCK-20260927-01`

---

## P-STOCK-20260927-02 — Add a market-session heartbeat and empty-day data manifest

- **Status:** PENDING
- **Type:** CODE
- **Target:** Daily evidence export and scheduler health instrumentation
- **Current:** The daily CSV folder is absent and contains no decision or trade rows, so inactivity cannot be separated from exporter or scheduler failure.
- **Proposed:** Generate a read-only daily manifest on every scheduled review date, including market-calendar status, collector start/end times, database read status, row counts by event type, export status, and explicit zero-row files or markers. This must not alter signals, orders, dashboard permissions, or paper-only mode.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Minimal; added files require retention and monitoring but do not affect model behavior.
- **Evidence:**
  - daily_csv.folder_exists=false.
  - Database path exists with no reported database error.
  - Dashboard reported market_open=false, but there is no daily artifact confirming normal closed-session handling.

**Approve in ChatGPT:**

`Approve P-STOCK-20260927-02`

**Decline in ChatGPT:**

`Decline P-STOCK-20260927-02`

---

## P-STOCK-20260927-03 — Capture decision-component telemetry before any calibration

- **Status:** PENDING
- **Type:** CODE
- **Target:** Per-evaluation decision logging
- **Current:** There are no decision rows, preventing analysis of symbol differences, threshold hit rates, confirmation behavior, buy/sell balance, VIX effects, or geo contribution.
- **Proposed:** For every symbol evaluation, log timestamp, market-session state, raw and adjusted score, distance from buy and sell thresholds, confirmation counters, proposed/final action, suppression reason, position state, VIX level and short-horizon changes, raw geo adjustment, applied geo adjustment, and all portfolio-control rejection reasons. Join later paper fills and realized P/L to the originating decision ID. Keep thresholds unchanged until at least 12 eligible observations exist for any calibration slice; require at least 12 observations per symbol before symbol-specific tuning.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Higher log volume and schema complexity; use versioned fields and avoid changing score computation while collecting the shadow sample.
- **Evidence:**
  - decisions.rows=0 and decisions.by_symbol is empty.
  - orders.rows=0, fills.rows=0, and realized.rows=0.
  - No causal attribution is possible for the configured 70/30 thresholds, two confirmations, VIX, or geo adjustment.

**Approve in ChatGPT:**

`Approve P-STOCK-20260927-03`

**Decline in ChatGPT:**

`Decline P-STOCK-20260927-03`

---

## P-STOCK-20260927-04 — Shadow-test geo freshness and headline deduplication

- **Status:** PENDING
- **Type:** CODE
- **Target:** Geo-feed health and contribution instrumentation
- **Current:** The geo artifact is eight days older than the review date, reports status 'ok', and contains apparent duplicate syndicated headlines while exposing a +7.1 adjustment.
- **Proposed:** Without changing the applied model score, compute and log feed age, newest-event age, duplicate-group IDs based on normalized title plus publication time, raw event count, deduplicated event count, raw adjustment, and a deduplicated shadow adjustment. Mark freshness as a separate health state rather than treating status='ok' as proof of recency. Evaluate at least 12 contemporaneous decision observations before considering any production weighting or freshness cutoff.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Normalization may merge legitimately distinct reports; keeping the result shadow-only avoids changing paper decisions while precision is measured.
- **Evidence:**
  - Geo generated_at=2026-09-19T16:41:18.944358+00:00 for review_date=2026-09-27.
  - The feed reports active_event_count=249 and score_adjustment=+7.1.
  - Repeated EnergyNow headlines share publication times and substantially identical content across domain variants.

**Approve in ChatGPT:**

`Approve P-STOCK-20260927-04`

**Decline in ChatGPT:**

`Decline P-STOCK-20260927-04`

---

## Quick command

`Review today's StockTracker proposals`
