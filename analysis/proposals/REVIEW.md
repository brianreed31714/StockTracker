# StockTracker Proposals — 2026-10-07

Paper-trading model improvement proposals. Human approval is required before implementation/deployment.

## P-STOCK-20261007-01 — Add a shadow near-miss opportunity and forward-outcome ledger

- **Status:** PENDING
- **Type:** CODE
- **Target:** Decision funnel instrumentation for all configured symbols
- **Current:** Daily maxima and aggregate gate counts are available, but near-threshold events are not joined to symbol-specific gates or subsequent prices. AMZN's exact blocker and TSLA/NVDA forward outcomes cannot be proven.
- **Proposed:** For every no-position decision with score at least 60, and every raw threshold crossing, write a SHADOW record containing symbol, event ID, score components, threshold distance, momentum, volume ratio, confirmation count, exact gate, VIX, geo adjustment, regime, and forward returns/MFE/MAE at 5, 15, 30, and 60 minutes. Report results per symbol only after at least 12 resolved events; do not alter execution thresholds.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Low instrumentation risk; additional log volume and delayed-price alignment must be monitored. Execution behavior remains unchanged.
- **Evidence:**
  - AMZN maximum score was 72.697 with no BUY.
  - TSLA maximum was 68.13 and NVDA maximum was 68.65.
  - Two BUY-side events awaited confirmation, but the supplied summary does not definitively join them to symbols.
  - Only three raw crossings and one realized trade are insufficient for calibration.

**Approve in ChatGPT:**

`Approve P-STOCK-20261007-01`

**Decline in ChatGPT:**

`Decline P-STOCK-20261007-01`

---

## P-STOCK-20261007-02 — Restore XLF/FAS/FAZ shadow snapshot, signal, and outcome publication

- **Status:** PENDING
- **Type:** CODE+CONFIG
- **Target:** financial_leverage_shadow pipeline
- **Current:** The feature is enabled with outcome horizons 5,15,30,60, but all three financial-leverage tables contain zero rows and the dashboard reports FINANCIAL_SNAPSHOT_UNAVAILABLE.
- **Proposed:** Add a startup/provider health check for XLF, FAS, and FAZ; publish one timestamped snapshot per evaluation cycle, including explicit provider/error status. When a shadow signal occurs, persist its score, regime, prices, and forward returns at configured horizons. Keep it non-executable and require at least 12 resolved signals before any calibration review.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Provider limitations or leveraged-ETF data quality could create misleading shadow signals; explicit freshness and error fields mitigate this.
- **Evidence:**
  - financial_leverage_shadow rows: 0.
  - financial_leverage_signals rows: 0.
  - financial_leverage_outcomes rows: 0.
  - The enabled feature produced no evidence despite 70 market-regime snapshots.

**Approve in ChatGPT:**

`Approve P-STOCK-20261007-02`

**Decline in ChatGPT:**

`Decline P-STOCK-20261007-02`

---

## P-STOCK-20261007-03 — Repair premarket gap and bias observability

- **Status:** PENDING
- **Type:** CODE
- **Target:** premarket_intelligence collection and publication
- **Current:** Premarket is enabled with five refresh offsets and a 60-minute context window, but the published table has zero rows and all latest gap/bias fields are null.
- **Proposed:** At each configured premarket offset, publish a row for every trade symbol with prior close, current premarket price, gap percentage, data freshness, provider status, computed bias, geo status, and an explicit social_status=UNAVAILABLE. Emit a failure row rather than silently producing no data. Keep premarket adjustments unchanged until at least 12 resolved sessions or qualifying events are available.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Premarket IEX coverage may be sparse; stale or absent quotes must be marked rather than imputed.
- **Evidence:**
  - premarket_intelligence rows: 0.
  - Premarket adjustment was 0.0 in every displayed top signal.
  - Social source is explicitly UNAVAILABLE.

**Approve in ChatGPT:**

`Approve P-STOCK-20261007-03`

**Decline in ChatGPT:**

`Decline P-STOCK-20261007-03`

---

## P-STOCK-20261007-04 — Evaluate volatility-normalized exits in parallel

- **Status:** PENDING
- **Type:** CODE+CONFIG
- **Target:** Paper position exit research
- **Current:** Paper execution uses fixed 2% stop-loss, 3% take-profit, 1% trailing activation, and 1.25% trailing distance without published ATR or entry-volatility context.
- **Proposed:** Run a SHADOW exit simulator beside each paper position using frozen-at-entry ATR or realized-volatility multiples. Log baseline versus shadow exit timestamp, reason, return, MFE, MAE, and holding time by symbol. Preserve all current execution exits and risk caps; require at least 12 closed comparable positions before considering any configuration change.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** ATR definitions and lookback choices can introduce research degrees of freedom; freeze the specification before collecting outcomes.
- **Evidence:**
  - TSLA and NVDA displayed elevated volume and are plausible high-volatility cases.
  - Only one realized XOM trade exists.
  - No ATR, range-normalized stop distance, or stop/target exit attribution was supplied.

**Approve in ChatGPT:**

`Approve P-STOCK-20261007-04`

**Decline in ChatGPT:**

`Decline P-STOCK-20261007-04`

---

## P-STOCK-20261007-05 — Add geo-score counterfactual attribution for XOM and GLD

- **Status:** PENDING
- **Type:** CODE
- **Target:** Geo context instrumentation
- **Current:** Geo adjustments materially affect XOM and GLD scores, but logs do not expose score-without-geo, event contribution weights, freshness, or subsequent outcome attribution.
- **Proposed:** For each XOM and GLD decision, persist the executed score, score excluding geo, contributing event IDs with age/direction/materiality, conflict ratio, and whether the threshold outcome changes without geo. Attach 15-, 30-, and 60-minute forward returns without changing the current geo adjustment.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Headline duplication and correlated events may overstate attribution; event IDs and conflict metrics should make this auditable.
- **Evidence:**
  - XOM average geo adjustment was +5.876 and its maximum score was 79.348.
  - GLD average geo adjustment was +1.469.
  - The feed's leading oil events included both bullish and bearish directions.
  - XOM supplied the only same-day realized P/L, which is insufficient to isolate geo value.

**Approve in ChatGPT:**

`Approve P-STOCK-20261007-05`

**Decline in ChatGPT:**

`Decline P-STOCK-20261007-05`

---

## P-STOCK-20261007-06 — Diagnose why ZPTA creates predictions but no shadow trades

- **Status:** PENDING
- **Type:** CODE
- **Target:** ZPTA shadow entry/exit funnel
- **Current:** ZPTA produced 300 predictions and 264 resolved predictions but zero shadow trades and zero exit reasons. Several model families report identical horizon metrics.
- **Proposed:** Publish a ZPTA funnel row for each evaluated bar with provider freshness, model score, 68-point entry comparison, liquidity gate, regime gate, duplicate-signal gate, final disposition, and model-specific label/outcome identifiers. Add a validation warning when distinct models have identical predictions or metrics across a session. Do not change the entry score until at least 12 closed shadow trades exist.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Diagnostic logging may reveal that delayed data cannot support timely shadow entries; it must not be used to bypass freshness or liquidity controls.
- **Evidence:**
  - ZPTA shadow trades: 0 despite 300 predictions.
  - Latest status was NO_NEW_BAR using yahoo_delayed.
  - Latest regime was LIQUIDITY_DANGER.
  - zpta_exit_reason_counts was empty and multiple model families had identical reported statistics.

**Approve in ChatGPT:**

`Approve P-STOCK-20261007-06`

**Decline in ChatGPT:**

`Decline P-STOCK-20261007-06`

---

## Quick command

`Review today's StockTracker proposals`
