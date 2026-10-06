# StockTracker Performance — Latest

Review date: **2026-10-06**
Generated: 2026-10-06T20:05:04.142858+00:00

## Paper-trading results

- Decisions: **3150**
- Orders: **0** (buys 0 / sells 0)
- Completed paper trades: **0**
- Realized paper P/L: **$+0.00**
- Win/loss: **0/0**
- Win rate: **n/a%**

## Review

The 2026-10-06 run remained PAPER ONLY and produced 3,150 decisions, all HOLD, with no same-day order attempts, accepted orders, fills, or realized trades. The evidence does not support threshold, confirmation, VIX, geo-weight, regime, premarket, or XLF/FAS/FAZ calibration. Instrumentation gaps prevent causal attribution: the decision funnel, order-attempt lineage, regime-decision linkage, financial-leverage evidence, premarket evidence, and shadow-trade tables are empty. Keep all model thresholds and risk controls unchanged while repairing SHADOW observability.

Data quality: **LIMITED**

### Supporting evidence

- Published files: **20**
- Published rows analyzed: **3361**
- Integrity status: **PASS**
- Integrity issues: **none**

### Findings
- Observed — Supporting-log integrity analysis passed and covered all 3,361 published rows across 15 analyzed tables. It found no duplicate decision event IDs, orphan order attempts, accepted attempts without order IDs, duplicate fill order IDs, unresolved ZPTA returns, or database error.
- Observed — Eleven analyzed tables were empty: orders, fills, realized, decision_funnel, order_attempts, regime_decision_shadow, all three financial-leverage tables, premarket_intelligence, and zpta_shadow_trades. Empty order-related tables make order_gate_counts empty; this is absence of events/evidence, not proof that every gate operated correctly.
- Observed — All 3,150 decisions were HOLD: 350 observations for each of nine symbols. There were zero BUY and zero SELL actions, so same-day buy/sell balance is 0/0 rather than a directional imbalance.
- Observed — XOM reached a maximum score of 70.274, above the configured buy threshold of 70, but no BUY occurred. The empty decision funnel means the evidence cannot determine whether this was an isolated raw crossing, failed two-cycle confirmation, portfolio-cap block, or another disposition. No symbol reached the sell threshold: the lowest observed score was WMT at 30.435, still above 30.
- Observed — No requested order notional, order attempt, accepted order, fill, or realized trade was recorded. Same-day realized P/L is therefore $0 from zero realized rows; this is not evidence of strategy profitability or loss avoidance.
- Observed — The dashboard snapshot separately shows three open positions (AAPL, SPY, XOM), $7,608.47 market exposure, and approximately $108.50 aggregate unrealized gain. Their opening provenance is absent from the same-day order/fill files, so they must not be treated as 2026-10-06 fills or realized performance.
- Observed — Per-symbol scores differed: XOM had the highest average score at 55.629 and NVDA the lowest at 47.896. Nevertheless, every symbol remained HOLD, and there are no realized outcomes for assessing symbol-specific efficacy.
- Observed — VIX was about 15.04 and its average score adjustments were small, ranging from -0.017 for GLD to +0.047 for NVDA and TSLA. There is no trade or forward-outcome evidence with which to estimate the VIX adjustment's effect.
- Observed — Geo contribution was concentrated in XOM (average +3.64 score) and GLD (average +0.91); other symbols averaged zero. The feed was healthy at generation time, but the top-event list contains repeated variants of the same WSJ and TradeWinds stories. No evidence isolates whether deduplication occurred before scoring or whether the geo uplift improved forward outcomes.
- Hypothesis — Duplicate or syndicated geo headlines may overstate event persistence or confidence, but the supplied data cannot establish that they were independently counted in the score.
- Observed — Market-regime SHADOW produced 70 rows, all RISK_ON with score 100, but regime_decision_shadow had zero rows. This one-state, one-day sample cannot validate regime gating or permit calibration.
- Observed — Financial-leverage SHADOW was enabled, but XLF/FAS/FAZ snapshots, signals, and outcomes were all absent; the dashboard reported FINANCIAL_SNAPSHOT_UNAVAILABLE. There is no leverage-signal or forward-outcome evidence to review.
- Observed — Premarket intelligence was enabled but logged zero rows, so there is no gap, bias, scheduled-refresh, or post-open outcome evidence. Social sentiment is explicitly unavailable and must not be inferred.
- Observed — ZPTA logged 9 observations, 132 prediction rows, and 108 resolved predictions with no missing resolved returns. Each model/horizon reports only 9 samples, below the minimum calibration target of 12. No ZPTA shadow trades occurred, and the delayed provider ended with NO_NEW_BAR.
- Observed — ZPTA breakout, pullback, and VWAP-reclaim variants reported 11.11% accuracy in their nine-sample sets, while exhaustion variants reported 55.56% to 77.78%; average underlying returns were negative. These tiny, potentially overlapping samples support continued observation only, not threshold or model tuning.

### Per-symbol paper P/L

- No completed trades for this review date.

### Current proposal count

- 6 proposal(s) drafted for human review.
