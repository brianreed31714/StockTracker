# StockTracker Proposals — 2026-10-02

Paper-trading model improvement proposals. Human approval is required before implementation/deployment.

## P-STOCK-20261002-01 — Add manifest file-count self-consistency validation

- **Status:** PENDING
- **Type:** CODE
- **Target:** Evidence publisher and integrity_analysis.json
- **Current:** The manifest reports 20 published files while the supplied files array contains 19 entries; integrity status remains PASS with no issue recorded.
- **Proposed:** At publication, compare published_file_count with the number of manifest file entries, require every entry to have path/bytes/SHA-256 metadata, and emit a named integrity issue on mismatch. Keep row-coverage checks separate so the valid 719-row analysis remains visible.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Low operational risk; a stricter check may mark otherwise usable evidence bundles LIMITED until the metadata discrepancy is corrected.
- **Evidence:**
  - published_file_count=20
  - The supplied files array enumerates 19 paths
  - all_published_rows_analyzed=719 and table_count=15
  - supporting_log_analysis.status=PASS with issues=[]

**Approve in ChatGPT:**

`Approve P-STOCK-20261002-01`

**Decline in ChatGPT:**

`Decline P-STOCK-20261002-01`

---

## P-STOCK-20261002-02 — Restore regime-to-decision shadow records

- **Status:** PENDING
- **Type:** CODE
- **Target:** regime_decision_shadow emitter
- **Current:** There are 15 market_regime_shadow snapshots and 648 decisions, but regime_decision_shadow has zero rows.
- **Proposed:** For every published decision, write a non-executing shadow record containing decision_event_id, symbol, timestamp, nearest regime snapshot ID/age, regime state/score, actual action, counterfactual regime-aware action, and explicit unavailable/stale reason. Do not let the counterfactual alter paper orders until multi-state forward-outcome evidence is accumulated.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Timestamp joins could be misleading if stale snapshots are silently attached; require snapshot age and an explicit staleness status.
- **Evidence:**
  - market_regime_shadow rows=15, all RISK_ON
  - decisions rows=648
  - regime_decision_shadow rows=0
  - No regime-conditioned symbol or action evidence exists

**Approve in ChatGPT:**

`Approve P-STOCK-20261002-02`

**Decline in ChatGPT:**

`Decline P-STOCK-20261002-02`

---

## P-STOCK-20261002-03 — Emit scheduled-run diagnostics for premarket and financial-leverage shadows

- **Status:** PENDING
- **Type:** CODE
- **Target:** premarket_intelligence and financial-leverage XLF/FAS/FAZ collectors
- **Current:** Both features are enabled, but premarket intelligence and all financial-leverage snapshot/signal/outcome tables are empty. The dashboard only exposes FINANCIAL_SNAPSHOT_UNAVAILABLE.
- **Proposed:** Write one diagnostic row for every scheduled refresh attempt, including scheduled timestamp, actual timestamp, process/session status, provider, symbol-level data availability, gap calculation status, geo status, social status=UNAVAILABLE, regime linkage, and terminal reason code. For XLF/FAS/FAZ, continue writing candidate snapshots and forward outcomes even when the candidate is NONE; do not generate paper orders.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Additional rows and provider calls could increase storage or rate-limit pressure; diagnostics should reuse scheduled fetches and record skipped calls rather than force retries.
- **Evidence:**
  - premarket_enabled=true but premarket_intelligence rows=0
  - financial_leverage_shadow_enabled=true but snapshot_rows=0, signal_rows=0, outcome_rows=0
  - Dashboard reason is FINANCIAL_SNAPSHOT_UNAVAILABLE
  - premarket_social_source=UNAVAILABLE
  - No premarket gap/bias or XLF/FAS/FAZ forward-outcome evidence is available

**Approve in ChatGPT:**

`Approve P-STOCK-20261002-03`

**Decline in ChatGPT:**

`Decline P-STOCK-20261002-03`

---

## P-STOCK-20261002-04 — Measure duplicate-aware geo adjustments in parallel

- **Status:** PENDING
- **Type:** CODE+CONFIG
- **Target:** Geo-feed normalization and XOM/GLD context instrumentation
- **Current:** The geo feed has 303 active events and applied approximately +5.36 to XOM, while top events contain several near-duplicate versions of the same tanker-loading story. Only the production paper score adjustment is logged.
- **Proposed:** Add a SHADOW-only duplicate cluster ID based on normalized headline, event time, canonical source/domain, and semantic similarity. Log raw event count, unique cluster count, current adjustment, duplicate-aware counterfactual adjustment, and subsequent XOM/GLD returns at fixed horizons. Do not change the active geo weight or cap until at least 12 independent event clusters with outcomes are available.
- **Confidence:** MEDIUM
- **Recommended mode:** SHADOW
- **Risk:** Over-aggressive clustering could merge distinct updates. Parallel scoring and retained cluster membership make the test reversible without affecting paper decisions.
- **Evidence:**
  - XOM average geo adjustment=5.362 versus average technical score=51.639
  - GLD average geo adjustment=1.341
  - Geo active_event_count=303 and score_adjustment=+5.36
  - Multiple top events repeat the Iranian tanker-loading headline across timestamps and source labels
  - No causal geo outcome table is supplied

**Approve in ChatGPT:**

`Approve P-STOCK-20261002-04`

**Decline in ChatGPT:**

`Decline P-STOCK-20261002-04`

---

## P-STOCK-20261002-05 — Log exit trigger and notional lifecycle fields

- **Status:** PENDING
- **Type:** CODE
- **Target:** Decision funnel, order attempts, orders, and fills
- **Current:** One TSLA SELL was accepted and filled, but raw_threshold_crossings=0 and the trigger class is absent. The order shows $2,591.61 sell notional without separate requested, accepted, and filled notionals or an explicit statement that the $2,500 cap is entry-only.
- **Proposed:** Attach a shared lifecycle ID and log trigger_class (score confirmation, stop, take profit, trailing stop, manual/system liquidation, or other), position quantity before exit, requested quantity/notional, cap type and applicability, accepted quantity/notional, filled quantity/notional, fill price, and realized-P/L linkage. Add consistency checks without changing exit behavior or any cap.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Schema changes require coordinated updates across log writers and readers; fields should initially be additive and nullable.
- **Evidence:**
  - decision_funnel: SELL=1, ORDER_ACCEPTED=1, ORDER_SUBMITTED=1
  - raw_threshold_crossings=0
  - orders: TSLA sell_notional=$2,591.61
  - max_trade_dollars=$2,500
  - One attempt, one accepted order, one fill, and one realized row exist

**Approve in ChatGPT:**

`Approve P-STOCK-20261002-05`

**Decline in ChatGPT:**

`Decline P-STOCK-20261002-05`

---

## P-STOCK-20261002-06 — Record ZPTA shadow-entry gate outcomes

- **Status:** PENDING
- **Type:** CODE
- **Target:** ZPTA prediction-to-shadow-trade funnel
- **Current:** ZPTA generated 48 predictions and resolved 24, but created zero shadow trades and supplies no exit-reason counts or entry-gate records.
- **Proposed:** For every prediction eligible for evaluation, write a gate record with model, horizon, score, entry threshold, bar freshness, provider delay, liquidity/regime status, position-size eligibility, final shadow disposition, and rejection reason. Continue collecting forward returns and do not alter zpta_entry_score=68 or zpta_max_position_dollars=$150 until each calibration cohort reaches at least 12 independent samples.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Predictions from the same three observations may be correlated; instrumentation must identify observation IDs so they are not treated as independent samples.
- **Evidence:**
  - prediction_rows=48 and resolved_predictions=24
  - shadow_trades=0 and closed_shadow_trades=0
  - zpta_exit_reason_counts is empty
  - Per-model sample sizes range from 1 to 3
  - Latest provider=yahoo_delayed and latest status=NO_NEW_BAR

**Approve in ChatGPT:**

`Approve P-STOCK-20261002-06`

**Decline in ChatGPT:**

`Decline P-STOCK-20261002-06`

---

## Quick command

`Review today's StockTracker proposals`
