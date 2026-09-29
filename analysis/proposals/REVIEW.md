# StockTracker Proposals — 2026-09-29

Paper-trading model improvement proposals. Human approval is required before implementation/deployment.

## P-STOCK-20260929-01 — Add crossing-level IDs and counterfactual outcome labels

- **Status:** PENDING
- **Type:** CODE
- **Target:** Decision funnel and threshold-crossing telemetry
- **Current:** The report contains three raw threshold crossings, four funnel rows, and only aggregate gate reasons. Non-executed crossings lack clearly linked forward outcomes and unique lifecycle identifiers.
- **Proposed:** In SHADOW, assign a stable event ID to every first threshold crossing and link its symbol, side, score, prior score, confirmation count, position eligibility, gate reason, order-attempt ID, and final disposition. Record 5-, 15-, 30-, and 60-minute forward returns for both submitted and non-submitted crossings. Report raw events separately from repeated confirmation observations. Do not alter the 70/30 thresholds or two-confirmation requirements until at least 12 eligible outcomes exist for the evaluated bucket.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Low operational risk because this is append-only SHADOW telemetry. Main risks are excess logging volume and incorrect forward-return timestamp alignment.
- **Evidence:**
  - Three raw threshold crossings were reported, while the funnel contained four rows split across two BUY and two SELL records.
  - Two funnel records awaited confirmation and two produced submitted orders.
  - AMZN exceeded 70 and WMT fell below 30 without corresponding decision actions in the aggregate table; supplied data does not show the complete eligibility lifecycle.

**Approve in ChatGPT:**

`Approve P-STOCK-20260929-01`

**Decline in ChatGPT:**

`Decline P-STOCK-20260929-01`

---

## P-STOCK-20260929-02 — Restore financial-leverage SHADOW snapshots with explicit feed-health fields

- **Status:** PENDING
- **Type:** CODE+CONFIG
- **Target:** XLF/FAS/FAZ financial_leverage_shadow data ingestion
- **Current:** The feature is enabled with a minimum score of 70 and outcome horizons of 5,15,30,60, but it produced zero snapshots, signals, and outcomes. XLF/FAS/FAZ premarket gaps were null, and the only reason was FINANCIAL_SNAPSHOT_UNAVAILABLE.
- **Proposed:** Repair read-only quote/bar acquisition for XLF, FAS, and FAZ and log per-symbol provider, timestamp, freshness, missing-field reason, and session status on every scheduled snapshot. Keep the feature SHADOW-only, retain the score threshold of 70, and suppress candidate scoring whenever any required input is stale or absent. Begin outcome collection only after valid snapshots are present; do not calibrate until at least 12 eligible signals are available.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** A provider repair could introduce inconsistent timestamps or delayed ETF data. Freshness validation and SHADOW-only operation limit model risk.
- **Evidence:**
  - Financial-leverage snapshot_rows, signal_rows, and outcome_rows were all zero.
  - The latest candidate was null and the dashboard reported FINANCIAL_SNAPSHOT_UNAVAILABLE.
  - Premarket gaps for XLF, FAS, and FAZ were null while SPY and QQQ gaps were populated.

**Approve in ChatGPT:**

`Approve P-STOCK-20260929-02`

**Decline in ChatGPT:**

`Decline P-STOCK-20260929-02`

---

## P-STOCK-20260929-03 — Audit geo deduplication and expose XOM score attribution

- **Status:** PENDING
- **Type:** CODE
- **Target:** Geo-feed canonicalization and geo score decomposition
- **Current:** The feed reports 278 active events and a negative aggregate signal. Apparent duplicate headlines occur in the top-event list, and XOM received negative geo adjustments despite multiple high-materiality events labeled bullish for crude and often bullish for XOM.
- **Proposed:** Run a parallel SHADOW geo calculation that canonicalizes source domains and normalizes title text, clusters likely duplicate stories, and logs each cluster's contribution separately for crude direction, XOM-specific direction, broader risk effect, confidence, recency, and final signed adjustment. Compare existing versus deduplicated adjustments without changing production paper decisions.
- **Confidence:** MEDIUM
- **Recommended mode:** SHADOW
- **Risk:** Over-aggressive clustering could merge genuinely distinct reports. The parallel calculation must not replace the current adjustment until enough comparisons and forward outcomes are available.
- **Evidence:**
  - Two Hormuz headlines appear under energynow.com and EnergyNow.com with the same publication timestamp and substantially identical content.
  - Two Kharg Island headlines similarly appear twice with capitalization differences.
  - XOM average geo adjustment was -0.372 and the dashboard value was -0.51, while several top events were classified bullish for XOM.
  - The aggregate geo signal was -0.0762 with a -0.76 score adjustment, so broader negative aggregation could legitimately differ from individual headline direction.

**Approve in ChatGPT:**

`Approve P-STOCK-20260929-03`

**Decline in ChatGPT:**

`Decline P-STOCK-20260929-03`

---

## P-STOCK-20260929-04 — Label premarket gap/bias outcomes and missing-symbol coverage

- **Status:** PENDING
- **Type:** CODE
- **Target:** Premarket intelligence telemetry
- **Current:** Five snapshots were all NEUTRAL; SPY and QQQ gaps were available, XLF/FAS/FAZ gaps were null, and no forward outcomes or per-refresh contribution records are supplied. Social sentiment is unavailable.
- **Proposed:** For each scheduled refresh, persist gap values, data freshness, bias inputs excluding social sentiment, resulting adjustment, and 5-, 15-, 30-, and 60-minute post-open returns for SPY and QQQ. Record explicit missing reasons for XLF/FAS/FAZ. Keep the current maximum adjustment, active window, and warmup unchanged, and prohibit calibration until at least 12 eligible premarket sessions or events are collected for the evaluated bucket.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Forward labels can be misleading if session boundaries or delayed quotes are misaligned. This proposal does not activate missing social data or alter paper decisions.
- **Evidence:**
  - Premarket intelligence had only five rows and all were NEUTRAL.
  - Latest SPY and QQQ gaps were +0.163% and +0.323%; XLF, FAS, and FAZ were null.
  - Premarket adjustments displayed in the dashboard were 0.0.
  - The social source and status were explicitly UNAVAILABLE.

**Approve in ChatGPT:**

`Approve P-STOCK-20260929-04`

**Decline in ChatGPT:**

`Decline P-STOCK-20260929-04`

---

## P-STOCK-20260929-05 — Add regime counterfactual outcomes before considering active gating

- **Status:** PENDING
- **Type:** CODE
- **Target:** Market-regime SHADOW evaluator
- **Current:** There were 75 RISK_ON observations with the same score of 85 and only two decision-shadow rows, both ALLOW_EQUITY for XOM. No state diversity or forward-outcome comparison is available.
- **Proposed:** Log regime state transitions rather than only repeated identical snapshots, and attach state, score components, hypothetical allow/block disposition, and forward returns to each eligible threshold event. Produce per-state counts and outcomes while leaving regime logic non-binding. Require at least 12 eligible events per evaluated state before any calibration proposal.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Regime states may remain highly imbalanced, delaying evaluation. No trading behavior changes because the evaluator remains SHADOW-only.
- **Evidence:**
  - All 75 regime observations were RISK_ON with average and latest score 85.
  - Only two regime-decision records existed, both for XOM and both ALLOW_EQUITY.
  - The latest regime inputs included positive long-term trend evidence but nonpositive SPY 20-day momentum, illustrating why component-level outcome attribution is useful.

**Approve in ChatGPT:**

`Approve P-STOCK-20260929-05`

**Decline in ChatGPT:**

`Decline P-STOCK-20260929-05`

---

## P-STOCK-20260929-06 — Instrument ZPTA bar freshness and no-trade gate reasons

- **Status:** PENDING
- **Type:** CODE
- **Target:** ZPTA SHADOW prediction and trade lifecycle
- **Current:** ZPTA used yahoo_delayed, ended with NO_NEW_BAR, generated 72 predictions and 56 resolutions, but produced no shadow trades. Each reported model/horizon cell has only four or five samples, and no detailed no-trade gate distribution is supplied.
- **Proposed:** Log expected versus received bar timestamps, provider delay, duplicate/no-new-bar reason, candidate entry score, each trade gate, and the final reason no shadow trade was opened. Keep zpta_entry_score at 68 and the $150 shadow position limit unchanged. Continue reporting outcomes by model and horizon, with calibration disabled until each evaluated cell reaches at least 12 samples.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Additional logs may expose provider timing noise but do not affect the main paper portfolio. Care is needed not to interpret correlated predictions as independent samples.
- **Evidence:**
  - Latest provider was yahoo_delayed and dashboard status was NO_NEW_BAR.
  - There were zero shadow trades and zero closed shadow trades.
  - Reported model/horizon samples were four or five, below the minimum calibration target of 12.
  - The latest ZPTA regime was LIQUIDITY_DANGER, but the supplied evidence does not show whether that state or another gate prevented trades.

**Approve in ChatGPT:**

`Approve P-STOCK-20260929-06`

**Decline in ChatGPT:**

`Decline P-STOCK-20260929-06`

---

## Quick command

`Review today's StockTracker proposals`
