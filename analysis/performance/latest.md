# StockTracker Performance — Latest

Review date: **2026-10-02**
Generated: 2026-10-02T20:05:03.632260+00:00

## Paper-trading results

- Decisions: **648**
- Orders: **1** (buys 0 / sells 1)
- Completed paper trades: **1**
- Realized paper P/L: **$+117.47**
- Win/loss: **1/0**
- Win rate: **100.0%**

## Review

The paper system was operational but the evidence window was short and sparse for causal review. Across 648 decisions, 647 were HOLD and one TSLA SELL produced one accepted order, one fill, and $117.47 realized paper profit. This single realization is not sufficient for calibration. No threshold, confirmation, portfolio-cap, loss-control, or execution-policy changes are supported. Recommended work is limited to SHADOW instrumentation and evidence-pipeline repairs while preserving paper=True, all portfolio/risk caps, and the read-only dashboard.

Data quality: **LIMITED**

### Supporting evidence

- Published files: **20**
- Published rows analyzed: **719**
- Integrity status: **PASS**
- Integrity issues: **none**

### Findings
- Observed: Supporting-log integrity reports PASS, no database error, and analysis of all 719 published tabular rows. It found zero duplicate decision IDs, orphan attempts, accepted attempts lacking order IDs, duplicate fill order IDs, or resolved ZPTA predictions lacking returns. The only order-gate count was ORDER_ACCEPTED=1.
- Observed integrity limitation: published_file_count is 20, but the supplied files array enumerates 19 paths. The 719-row total is internally reproducible across the 15 tabular files, but file-manifest coverage cannot be considered fully self-consistent without explaining the missing twentieth entry.
- Observed: Six tables are empty: regime_decision_shadow, financial_leverage_shadow, financial_leverage_signals, financial_leverage_outcomes, premarket_intelligence, and zpta_shadow_trades. Thus there is no regime-to-decision counterfactual evidence, no XLF/FAS/FAZ signal or forward-outcome evidence, no premarket gap/bias evidence, and no ZPTA shadow-trade P/L evidence.
- Observed: Decision balance was 647 HOLD, zero BUY, and one SELL. Every symbol had 72 evaluations. Maximum scores remained below the 70 buy threshold: TSLA 69.162, XOM 68.573, AMZN 67.981, and all others lower. This same-day window therefore supplies no buy-side accepted-order evidence and only one sell-side event.
- Observed: The TSLA lifecycle contains one SELL decision, one accepted attempt, one submitted order, one fill, and one realized row. Realized paper P/L was +$117.47. The 100% win rate is based on one realization and must not be generalized. Separately, the dashboard snapshot showed three open positions, $7,571.06 exposure, and approximately $71.09 unrealized profit; these snapshot values are not realized results or new orders.
- Observed instrumentation ambiguity: the decision funnel reports one SELL submitted and accepted but raw_threshold_crossings=0. The evidence does not identify whether the SELL came from score confirmation, stop loss, take profit, trailing stop, or another position-exit rule.
- Observed notional distinction: the recorded TSLA sell order notional was $2,591.61, above max_trade_dollars=$2,500. This may simply be a full-position exit for which the entry-size cap is not applicable; the logs do not expose requested notional, cap applicability, accepted quantity/notional, and filled notional separately enough to verify that interpretation.
- Observed per-symbol context: XOM had the highest average score, 57.124, with average technical score 51.639 and average geo adjustment 5.362. GLD's average geo adjustment was 1.341; other symbols had zero. XOM's geo component was therefore material relative to its final score, but no same-day counterfactual outcome evidence establishes that it improved decisions.
- Observed geo-feed issue: the feed was healthy at generation time with no tail errors, but 30 warnings were present. Several top events are duplicate or near-duplicate versions of the same Iranian tanker-loading headline. With 303 active events and a +5.36 adjustment, duplicate concentration could amplify context; this is a hypothesis, not a demonstrated scoring error.
- Observed: VIX was approximately 15.42 and the regime shadow labeled all 15 snapshots RISK_ON with score 85. VIX adjustments in symbol averages were very small, roughly +0.022 to +0.087 except GLD at -0.030. Since only one regime state occurred and regime_decision_shadow is empty, no VIX or regime calibration is supported.
- Observed: Premarket was enabled but produced zero rows and all displayed premarket adjustments were 0.0. The evidence begins late in the session, so it cannot distinguish a scheduling failure from a process that was not running during the premarket window. Social sentiment is unavailable because premarket_social_source is explicitly UNAVAILABLE.
- Observed: Financial-leverage shadow was enabled, but the dashboard reported FINANCIAL_SNAPSHOT_UNAVAILABLE and all XLF/FAS/FAZ snapshot, signal, and outcome tables were empty. No leveraged-financial threshold or selection change is supportable.
- Observed: ZPTA produced 3 observations, 48 predictions, and 24 resolved prediction rows, but each model/horizon summary has only 1-3 samples and there were zero shadow trades. Every model is below the minimum calibration target of 12 samples, so entry score 68 and other ZPTA thresholds should remain unchanged.
- Hypothesis: Zero ZPTA trades despite 48 predictions could reflect valid entry gating rather than a defect. Gate-level records are absent, so causal attribution is not possible.
- Conclusion: The evidence supports instrumentation repairs, not model tuning. In particular, buy/sell thresholds, confirmations, VIX/geo weights, ZPTA entry score, stops, profit targets, and exposure limits should not be changed from this sample.

### Per-symbol paper P/L

- TSLA: 1 completed, $+117.47

### Current proposal count

- 6 proposal(s) drafted for human review.
