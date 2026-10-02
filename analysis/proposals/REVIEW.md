# StockTracker Proposals — 2026-10-01

Paper-trading model improvement proposals. Human approval is required before implementation/deployment.

## P-STOCK-20261001-01 — Restore XLF/FAS/FAZ SHADOW coverage with explicit availability rows

- **Status:** PENDING
- **Type:** CODE+CONFIG
- **Target:** financial-leverage SHADOW collector and XLF/FAS/FAZ premarket preflight
- **Current:** Financial-leverage snapshot, signal, and outcome tables contain zero rows; premarket gaps for XLF, FAS, and FAZ are null despite financial_leverage_shadow_enabled=true.
- **Proposed:** On every scheduled SHADOW cycle, write one status row per XLF/FAS/FAZ containing provider, quote/bar timestamp, availability, stale age, and failure reason. Emit candidate snapshots only from valid inputs and attach 5/15/30/60-minute outcomes when due. Keep all financial-leverage actions non-ordering and SHADOW-only.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Low operational risk; may increase log volume. It must not synthesize signals from stale or missing prices.
- **Evidence:**
  - All three financial-leverage tables are empty.
  - Premarket XLF/FAS/FAZ gap values are null.
  - The dashboard reports FINANCIAL_SNAPSHOT_UNAVAILABLE.

**Approve in ChatGPT:**

`Approve P-STOCK-20261001-01`

**Decline in ChatGPT:**

`Decline P-STOCK-20261001-01`

---

## P-STOCK-20261001-02 — Make funnel crossings and order lifecycle stages explicitly reconcilable

- **Status:** PENDING
- **Type:** CODE
- **Target:** decision_funnel and order_attempt instrumentation
- **Current:** The funnel reports 13 raw crossings but 14 side-classified rows. Aggregate records distinguish blocked and accepted attempts, but the supplied review cannot identify the extra non-crossing event or fully join requested notional, acceptance, fill, and realization stages.
- **Proposed:** Add immutable fields for raw_threshold_crossed, confirmation_sequence_id, confirmation_count, gate_evaluated, requested_notional, projected_pretrade_exposure, projected_position_count, attempt_status, order_id, fill_id, and realized_lot_id. Add daily reconciliation assertions that report rather than alter trading behavior.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Schema migration and downstream-report compatibility risk; no model behavior should change.
- **Evidence:**
  - Funnel rows=14 and side totals=14, while raw_threshold_crossings=13.
  - Gate counts reconcile to 2 ORDER_ACCEPTED and 2 MAX_OPEN_POSITIONS.
  - There were 2 orders, 2 fills, and only 1 realized record, which are valid distinct lifecycle counts.

**Approve in ChatGPT:**

`Approve P-STOCK-20261001-02`

**Decline in ChatGPT:**

`Decline P-STOCK-20261001-02`

---

## P-STOCK-20261001-03 — Add component-level forward attribution for geo, VIX, and premarket context

- **Status:** PENDING
- **Type:** CODE
- **Target:** decision SHADOW outcome instrumentation
- **Current:** Decision rows record component adjustments, but evidence does not provide component-tagged forward outcomes or counterfactual scores without each adjustment.
- **Proposed:** For each decision snapshot, log the technical-only score, score with each context component added separately, final score, threshold-crossing counterfactuals, and 5/15/30/60-minute symbol returns. Deduplicate highly correlated minute observations into independent event episodes and require at least 12 completed episodes per symbol/component before considering calibration.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Counterfactuals may still be confounded and must not be interpreted as causal without sufficient independent episodes.
- **Evidence:**
  - XOM average geo adjustment was 2.932 and its score reached 79.632 without a final action.
  - GLD average geo adjustment was 0.733.
  - Average VIX adjustments were near zero.
  - Five premarket snapshots were BULLISH, but no tagged outcomes were supplied.

**Approve in ChatGPT:**

`Approve P-STOCK-20261001-03`

**Decline in ChatGPT:**

`Decline P-STOCK-20261001-03`

---

## P-STOCK-20261001-04 — Instrument ZPTA trigger-conditioned outcomes and no-trade reasons

- **Status:** PENDING
- **Type:** CODE
- **Target:** ZPTA SHADOW prediction and shadow-trade pipeline
- **Current:** There are 300 predictions and 272 resolved predictions, but zero shadow trades and no exit reasons. Models at the same horizon share identical sample counts and average returns, obscuring model-specific trigger performance.
- **Proposed:** Record per-model eligibility, trigger timestamp, score-threshold result, ensemble contribution, entry suppression reason, hypothetical entry price, horizon return, and hypothetical exit reason. Generate shadow-trade rows only for valid trigger-conditioned cases; preserve zpta_shadow_enabled=true and prohibit order routing because the asset is non-tradable in preflight.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Hypothetical fills could overstate executable performance, especially with delayed OTC data; label them explicitly as non-executable SHADOW results.
- **Evidence:**
  - zpta_shadow_trades is empty and zpta_exit_reason_counts is empty.
  - Asset preflight says tradable=false.
  - All model families at each horizon show identical sample counts and average returns despite differing stated logic.
  - Latest ensemble action was FLAT at 47.8 versus a configured entry score of 68.

**Approve in ChatGPT:**

`Approve P-STOCK-20261001-04`

**Decline in ChatGPT:**

`Decline P-STOCK-20261001-04`

---

## P-STOCK-20261001-05 — Log cap headroom separately for cost basis and mark-to-market exposure

- **Status:** PENDING
- **Type:** CODE
- **Target:** portfolio-risk telemetry and read-only dashboard
- **Current:** The dashboard snapshot shows $10,006.84 exposure against a $10,000 cap, while two attempts were blocked by position count. The evidence does not show whether the exposure excess was market drift or an order-sizing breach.
- **Proposed:** Expose read-only fields for accepted-order cost basis, current market-value exposure, pre-order headroom, projected post-fill exposure, and cap-block reason. Retain max_total_exposure=$10,000, max_open_positions=4, max_daily_realized_loss=$300, and all existing enforcement behavior.
- **Confidence:** HIGH
- **Recommended mode:** PAPER
- **Risk:** Low; ensure dashboard calculations do not become an alternate source of truth for order enforcement.
- **Evidence:**
  - Dashboard market-value exposure was $10,006.84 with four open positions.
  - Two attempts were blocked by MAX_OPEN_POSITIONS.
  - Only one new buy order was accepted, with $2,500 requested notional.

**Approve in ChatGPT:**

`Approve P-STOCK-20261001-05`

**Decline in ChatGPT:**

`Decline P-STOCK-20261001-05`

---

## P-STOCK-20261001-06 — Continue regime evidence collection without activating a regime gate

- **Status:** PENDING
- **Type:** RESEARCH
- **Target:** market-regime SHADOW evaluation
- **Current:** All 66 regime snapshots were RISK_ON and all 11 mapped actions were ALLOW_EQUITY, providing no contrasting-state evidence.
- **Proposed:** Continue SHADOW logging and report decision/outcome cohorts by regime only after multiple states occur, including the number of independent decision episodes and 5/15/30/60-minute outcomes. Do not alter order eligibility until at least 12 independent mapped outcomes exist in each regime being compared.
- **Confidence:** HIGH
- **Recommended mode:** SHADOW
- **Risk:** Regime labels may remain imbalanced for extended periods; no paper-order behavior should be changed from this proposal.
- **Evidence:**
  - RISK_ON accounted for 66/66 snapshots.
  - ALLOW_EQUITY accounted for 11/11 mapped decisions.
  - Latest regime score was 85 with VIX below stress.

**Approve in ChatGPT:**

`Approve P-STOCK-20261001-06`

**Decline in ChatGPT:**

`Decline P-STOCK-20261001-06`

---

## Quick command

`Review today's StockTracker proposals`
