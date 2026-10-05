# StockTracker Performance — Latest

Review date: **2026-10-05**
Generated: 2026-10-05T20:05:03.791607+00:00

## Paper-trading results

- Decisions: **1116**
- Orders: **0** (buys 0 / sells 0)
- Completed paper trades: **0**
- Realized paper P/L: **$+0.00**
- Win/loss: **0/0**
- Win rate: **n/a%**

## Review

The paper model generated 1,116 decisions across nine symbols, all HOLD, with no same-day order, fill, or realized-trade records. Therefore, realized performance, execution quality, requested notional, accepted-order rates, and buy/sell effectiveness cannot be evaluated. Score distributions explain the lack of buys because every symbol remained below the 70 buy threshold; AMZN did fall below the 30 sell threshold, but no AMZN position was shown and the empty decision funnel prevents evaluating raw crossing and eligibility logic. The dashboard's three positions and approximately $78.91 combined unrealized gain are a point-in-time snapshot, not same-day fills or realized P/L. Evidence supports instrumentation repairs and continued SHADOW collection, not threshold calibration.

Data quality: **LIMITED**

### Supporting evidence

- Published files: **20**
- Published rows analyzed: **1309**
- Integrity status: **PASS**
- Integrity issues: **none**

### Findings
- Observed: Supporting-log analysis reports PASS with no listed integrity issues, no database error, and coverage of all 1,309 published rows. Those rows reconcile as 1,116 decisions, 25 regime snapshots, 12 ZPTA observations, and 156 ZPTA predictions.
- Observed integrity caveat: the manifest declares 20 published files, but the supplied files array contains 19 entries. This does not alter the reconciled 1,309 row count, but the file-count discrepancy should be validated.
- Observed: Eleven tables are empty, including orders, fills, realized, decision_funnel, order_attempts, regime_decision_shadow, all three financial-leverage tables, premarket_intelligence, and zpta_shadow_trades. Empty order_gate_counts and exit-reason counts reflect absent rows and do not demonstrate that gates or exits operated correctly.
- Observed: All 1,116 decisions were HOLD. Each symbol had 124 observations. No symbol reached the 70 buy threshold; maximum scores ranged from 60.313 for AAPL to 67.960 for XOM. AMZN reached 24.685, below the 30 sell threshold, but there was no displayed AMZN position and no funnel record to distinguish a raw crossing from an ineligible sell.
- Observed: There were no recorded order attempts, requested notionals, accepted orders, order IDs, fills, or realized trades. The reported realized P/L of $0 corresponds to an empty realized table and must not be interpreted as evidence of flat strategy performance.
- Observed: The dashboard snapshot showed three existing positions—AAPL, SPY, and XOM—with exposure of $7,578.88 and combined unrealized P/L of about $78.91. Their acquisition date and order provenance are unavailable, so they cannot be attributed to today's decisions.
- Observed: Buy/sell balance cannot be assessed beyond zero recorded actions on both sides. Likewise, per-symbol realized outcomes and hit rates are unavailable.
- Observed: VIX adjustments were very small on average by symbol, approximately -0.007 to +0.002, while the latest VIX was 15.54. No counterfactual or realized evidence supports changing VIX sensitivity.
- Observed: Geo contribution was concentrated in XOM and GLD. XOM averaged +2.561 geo points and GLD +0.640; the latest geo feed showed a +2.92 adjustment. XOM still remained below the buy threshold. Duplicate or near-duplicate Hormuz headlines appear among top events, so contribution independence is uncertain. No outcome evidence establishes causal value.
- Observed: Market-regime SHADOW produced 25 of 25 RISK_ON states, all scored 100, but regime_decision_shadow has zero rows. Thus state stability was observed only during the roughly two-hour decision-log window; its effect on decisions or forward outcomes is unknown.
- Observed: Financial-leverage SHADOW was enabled but produced no XLF/FAS/FAZ snapshots, signals, or 5/15/30/60-minute outcomes. The dashboard explicitly reported FINANCIAL_SNAPSHOT_UNAVAILABLE, so no leveraged-financial conclusion is supported.
- Observed: Premarket intelligence was enabled but produced zero rows and no gap or bias evidence. The available evidence does not establish whether the process was running during the configured premarket window. Social sentiment is unavailable because premarket_social_source is explicitly UNAVAILABLE.
- Observed: ZPTA had 12 observations, 156 predictions, and 128 resolved predictions with no missing resolved returns. Only 5-minute model summaries reached the minimum calibration sample of 12; 15- and 60-minute summaries had 10. The single-day samples are highly limited, model families report identical average returns within each horizon, and there were no shadow trades, so no threshold or model-weight change is justified.
- Hypothesis: Missing funnel, premarket, financial-leverage, and shadow-trade rows may reflect process start time, unavailable upstream data, or incomplete emit paths. The evidence does not identify which cause applies.
- Conclusion: Do not change the 70/30 thresholds, confirmation counts, stops, exposure caps, daily-loss control, or other trading parameters from this evidence. Keep paper=True and the dashboard read-only.

### Per-symbol paper P/L

- No completed trades for this review date.

### Current proposal count

- 6 proposal(s) drafted for human review.
