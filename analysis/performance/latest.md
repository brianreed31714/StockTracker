# StockTracker Performance — Latest

Review date: **2026-10-01**
Generated: 2026-10-02T00:47:56.346531+00:00

## Paper-trading results

- Decisions: **2935**
- Orders: **2** (buys 1 / sells 1)
- Completed paper trades: **1**
- Realized paper P/L: **$+0.91**
- Win/loss: **1/0**
- Win rate: **100.0%**

## Review

Supporting-log integrity passed across all 3,362 published rows, but model-performance evidence is limited: only 2 accepted paper orders, 2 fills, and 1 realized close occurred. No threshold, confirmation, risk-cap, or exit-rule changes are justified. Keep the system PAPER ONLY and prioritize SHADOW attribution and missing-pipeline instrumentation.

Data quality: **LIMITED**

### Supporting evidence

- Published files: **20**
- Published rows analyzed: **3362**
- Integrity status: **PASS**
- Integrity issues: **none**

### Findings
- Observed: integrity analysis covered all 3,362 published rows across 15 analyzed tables and reported no duplicate decision IDs, orphan attempts, accepted attempts lacking order IDs, duplicate fill order IDs, unresolved ZPTA returns, or database errors.
- Observed: four tables were empty: financial_leverage_shadow, financial_leverage_signals, financial_leverage_outcomes, and zpta_shadow_trades. Therefore there is no XLF/FAS/FAZ signal or forward-outcome evidence and no ZPTA shadow-trade P/L evidence.
- Observed: 2,935 decisions produced 3 BUY, 1 SELL, and 2,931 HOLD actions. The funnel recorded 13 raw threshold crossings, while its side counts total 14 events (11 BUY and 3 SELL); this likely reflects one non-crossing funnel event, but the supplied aggregates do not identify it.
- Observed: funnel dispositions were 2 submitted, 10 awaiting confirmation, and 2 rejected by MAX_OPEN_POSITIONS. Order-attempt logs show 2 accepted submissions and 2 blocks before submission, with no submit failures. These gate counts agree with supporting-log analysis.
- Observed: accepted-order activity was balanced at one paper buy and one paper sell. The AAPL buy requested $2,500; the AMZN sell shows $2,500.85 notional. Both accepted orders filled. Only the AMZN close generated realized P/L: +$0.91. This single realization is insufficient for performance or threshold calibration.
- Observed: the dashboard's $10,006.84 exposure is a mark-to-market snapshot across four open positions, not requested order notional. It is $6.84 above the configured $10,000 cap, plausibly due to price movement; the evidence does not establish that a new order breached the pre-trade cap. The four-position cap did block two later attempts.
- Observed: symbol threshold behavior differed. XOM had the highest average score (54.683), maximum 79.632, and average geo adjustment 2.932 but no final BUY/SELL action. TSLA reached 78.849 without a final action. AAPL, AMZN, and NVDA generated BUY actions; AMZN generated the only SELL. Confirmation and position gates prevent interpreting score maxima as orders.
- Observed: VIX adjustments were negligible on average by symbol, approximately -0.005 to +0.011. VIX was 16.38 at the dashboard snapshot. No evidence supports changing VIX sensitivity.
- Observed: geo context materially affected XOM and, to a lesser degree, GLD. The geo feed had 239 active events, no logged errors, 43 warnings, and conflicting bullish and bearish oil headlines. No component-level forward outcomes isolate geo contribution, so its causal value is unknown.
- Observed: premarket produced five BULLISH snapshots, with SPY +0.328% and QQQ +0.573% gaps, but XLF/FAS/FAZ gaps were null. The end-of-day dashboard showed premarket adjustment 0.0, consistent with the configured 60-minute active window, but no tagged forward outcomes establish whether the early bias helped.
- Observed: social sentiment was explicitly unavailable. It must not be treated as a model input for this review.
- Observed: market-regime SHADOW recorded 66 of 66 snapshots as RISK_ON and all 11 mapped decisions as ALLOW_EQUITY. This confirms operation in one regime only, not effectiveness across regimes or of a regime gate.
- Observed: ZPTA remained SHADOW-only, used delayed Yahoo data, and its asset preflight was active but non-tradable. It generated 300 predictions and 272 resolved predictions but zero shadow trades. Each model at a given horizon has identical sample count and average return, suggesting shared underlying forward-return labels rather than model-trigger-specific trade outcomes; this is a hypothesis requiring instrumentation review.
- Observed: ZPTA continuation/pullback/reclaim accuracy was 29.17%-35% with negative average forward returns, while exhaustion accuracy was 60%-70.83% under the same negative returns. These samples exceed 12 per reported model/horizon, but one day, shared observations, no shadow trades, and unclear trigger conditioning make threshold calibration unsafe.

### Per-symbol paper P/L

- AMZN: 1 completed, $+0.91

### Current proposal count

- 6 proposal(s) drafted for human review.
