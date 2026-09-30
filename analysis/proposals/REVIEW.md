# StockTracker Proposals — 2026-09-30

Paper-trading model improvement proposals. Human approval is required before implementation/deployment.

## P-STOCK-20260930-01 — Reconcile funnel counts and attach forward outcomes to every threshold event

- **Status:** PENDING
- **Type:** CODE
- **Target:** Decision-funnel audit and outcome instrumentation
- **Current:** The funnel reports 22 raw threshold crossings, but BUY/SELL side counts total 23. Records show gate dispositions but no matched 5/15/30/60-minute forward returns for accepted, confirmation-filtered, or position-cap-blocked events.
- **Proposed:** Add a stable event ID linking decision, threshold crossing, confirmation state, gate result, order attempt, and fill. Enforce and report count invariants, including raw crossings by side. In SHADOW, record 5/15/30/60-minute forward returns and score components for every crossing, including blocked candidates. Do not alter thresholds, confirmations, portfolio caps, or order behavior until at least 12 resolved observations exist for the evaluated segment.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Low implementation risk if logging is asynchronous. Incorrect event joins could misattribute outcomes, so invariant failures should be surfaced without affecting paper orders.
- **Evidence:**
  - The reported raw-crossing count is 22 while funnel side counts sum to 23.
  - Fourteen records awaited confirmation, six were blocked by MAX_OPEN_POSITIONS, and three produced submitted orders.
  - Only one realized trade exists, so accepted-order P/L cannot evaluate the larger candidate set.

**Approve in ChatGPT:**

`Approve P-STOCK-20260930-01`

**Decline in ChatGPT:**

`Decline P-STOCK-20260930-01`

---

## P-STOCK-20260930-02 — Restore XLF/FAS/FAZ financial-leverage SHADOW data capture

- **Status:** PENDING
- **Type:** CODE+CONFIG
- **Target:** financial_leverage_shadow market-data diagnostics and snapshots
- **Current:** The feature is enabled with a minimum score of 70 and outcome horizons of 5,15,30,60 minutes, but it generated zero snapshots, signals, or outcomes. Premarket XLF/FAS/FAZ gaps were null and the dashboard reported FINANCIAL_SNAPSHOT_UNAVAILABLE.
- **Proposed:** Add per-symbol quote/bar diagnostics for XLF, FAS, and FAZ, including provider, timestamp, bar age, missing-field reason, and IEX entitlement/coverage status. Permit a configured research-only fallback data provider if primary data are unavailable, while labeling provider and latency. Resume SHADOW snapshots and horizon outcomes only; retain the 70 score floor and prohibit paper order routing from this module.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Fallback data may differ in latency or price construction from IEX. Provider identity and bar age must therefore remain part of every observation.
- **Evidence:**
  - Financial-leverage snapshot_rows, signal_rows, and outcome_rows were all zero.
  - The latest candidate was null and the dashboard reason was FINANCIAL_SNAPSHOT_UNAVAILABLE.
  - All three financial ETF premarket gaps were null.

**Approve in ChatGPT:**

`Approve P-STOCK-20260930-02`

**Decline in ChatGPT:**

`Decline P-STOCK-20260930-02`

---

## P-STOCK-20260930-03 — Run a deduplicated geo-adjustment counterfactual alongside the active score

- **Status:** PENDING
- **Type:** CODE
- **Target:** Geo-feed event aggregation for XOM and GLD
- **Current:** The geo feed had 301 active events and a +3.97 current adjustment. XOM averaged +3.221 and GLD +0.804. The top-event list contains repeated or near-duplicate reports of the same incidents, but deduplication details and component outcomes are unavailable.
- **Proposed:** Cluster geo headlines by normalized incident, publication time, category, and source lineage. Log raw-event count, unique-cluster count, source concentration, active adjustment, and a deduplicated SHADOW adjustment side by side. Capture XOM and GLD forward returns at 5/15/30/60 minutes after material cluster changes. Do not replace the active adjustment or tune its cap from this one-day sample.
- **Confidence:** MEDIUM
- **Recommended mode:** SHADOW
- **Risk:** Over-aggressive clustering could merge distinct developments. The initial implementation should be observational and preserve the existing paper score.
- **Evidence:**
  - Multiple top entries repeat the TradeWinds Hormuz attack report and the EnergyNow Saudi output report.
  - XOM's average geo contribution was substantially larger than all non-energy symbols.
  - No geo-conditioned forward outcomes were supplied.

**Approve in ChatGPT:**

`Approve P-STOCK-20260930-03`

**Decline in ChatGPT:**

`Decline P-STOCK-20260930-03`

---

## P-STOCK-20260930-04 — Measure premarket bias, gaps, regime, and VIX against opening-window outcomes

- **Status:** PENDING
- **Type:** CODE
- **Target:** Premarket context attribution ledger
- **Current:** Five premarket snapshots were all BULLISH with score 75 and small positive SPY/QQQ gaps. Social data were unavailable, XLF/FAS/FAZ gaps were missing, and later dashboard records showed zero premarket adjustment. No matched opening-window outcomes were provided.
- **Proposed:** For each scheduled premarket refresh, persist available gaps, missing-gap reasons, bias inputs, regime state, VIX level, geo score, social-source status, calculated adjustment, and actual application/expiry timestamps. Resolve SPY, QQQ, and trade-symbol returns at market open plus 5/15/30/60 minutes. Keep the current maximum adjustment, 60-minute active window, and 20-minute warmup unchanged until at least 12 resolved sessions or otherwise appropriate independent observations are available.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Intraday observations from one session are correlated and must not be treated as independent daily samples. Instrumentation should distinguish sessions from refresh records.
- **Evidence:**
  - Premarket rows totaled only five and all had the same BULLISH classification.
  - SPY and QQQ gaps were +0.272% and +0.386%; financial ETF gaps were null.
  - Social source and status were UNAVAILABLE.
  - Regime observations were exclusively RISK_ON and VIX was 16.17, preventing separation of their effects without matched outcomes.

**Approve in ChatGPT:**

`Approve P-STOCK-20260930-04`

**Decline in ChatGPT:**

`Decline P-STOCK-20260930-04`

---

## P-STOCK-20260930-05 — Add ZPTA bar-freshness qualification and defer calibration

- **Status:** PENDING
- **Type:** CODE
- **Target:** ZPTA SHADOW prediction quality controls
- **Current:** Each reported model/horizon cell has only 7 or 8 samples, no shadow trades closed, and the latest state was NO_NEW_BAR using yahoo_delayed data. Existing metrics do not state whether stale bars were included in evaluated predictions.
- **Proposed:** Record bar age, expected interval, provider latency, and freshness status for every ZPTA prediction. Mark stale or NO_NEW_BAR predictions as data-quality-ineligible for calibration while retaining them in an audit stream. Continue collecting fresh resolved predictions until each model/horizon under review has at least 12 eligible samples; leave the entry score of 68 and $150 shadow position limit unchanged.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** A strict freshness rule could reduce sample accumulation. It should therefore label and separate observations rather than stop the SHADOW collector.
- **Evidence:**
  - Reported model sample sizes are below the minimum calibration target of 12.
  - Latest provider was yahoo_delayed and latest status was NO_NEW_BAR.
  - There were zero shadow trades and zero closed shadow trades, so no strategy-level P/L evidence exists.

**Approve in ChatGPT:**

`Approve P-STOCK-20260930-05`

**Decline in ChatGPT:**

`Decline P-STOCK-20260930-05`

---

## Quick command

`Review today's StockTracker proposals`
