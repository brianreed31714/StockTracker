# StockTracker Performance — Latest

Review date: **2026-09-30**
Generated: 2026-09-30T20:30:03.687320+00:00

## Paper-trading results

- Decisions: **3325**
- Orders: **3** (buys 2 / sells 1)
- Completed paper trades: **1**
- Realized paper P/L: **$-2.25**
- Win/loss: **0/1**
- Win rate: **0.0%**

## Review

The paper system operated within its configured exposure, position, trade-count, and daily-loss controls, but same-day evidence is insufficient for model calibration. Activity was sparse: 23 funnel records produced 3 accepted paper orders and one realized AAPL loss of $2.25. Signals were strongly buy-skewed, concentrated in TSLA, while the four-position cap blocked six submissions. Regime, premarket, VIX, geo, and ZPTA observations lack enough matched forward outcomes for causal conclusions. No trading thresholds or risk caps should be changed today.

Data quality: **LIMITED**

### Findings
- Observed: 3,325 decisions consisted of 3,316 HOLD, 8 BUY, and 1 SELL actions. The funnel reports 22 raw threshold crossings, approximately 0.66% of decision rows, although its side counts total 23 (22 BUY and 1 SELL); this reconciliation mismatch should be investigated.
- Observed: Signal direction was highly asymmetric. TSLA generated 5 of 8 BUY decisions; AAPL generated the only SELL and one BUY. Only AAPL and TSLA received same-day orders. Hypothesis: the imbalance may reflect the day's bullish conditions rather than threshold bias; one day cannot distinguish these explanations.
- Observed: Confirmation filtered 14 funnel records, while the maximum-open-position gate blocked 6 submissions. Three submissions were accepted without submit failures. The dashboard showed four open positions and $8,233.08 exposure, below the $10,000 exposure cap. There is no evidence supporting relaxation of the four-position cap.
- Observed: Realized evidence is only one closed AAPL paper trade with a $2.25 loss. Unrealized results at the dashboard snapshot were mixed across AMZN, SPY, TSLA, and XOM. This sample cannot support changes to entry, exit, stop-loss, take-profit, or confirmation settings.
- Observed: Market-regime SHADOW produced 74 observations, all RISK_ON with score 100, and 22 associated decisions all allowed equity. There is no contrasting regime sample, so regime effectiveness or calibration cannot be evaluated.
- Observed: VIX was 16.17 and below the regime stress condition. Average VIX adjustments were small across symbols, ranging from about -0.022 to +0.008, but no matched counterfactual or forward-outcome evidence isolates their effect.
- Observed: The geo feed was live and contributed materially to energy-linked scoring: XOM averaged a +3.221 geo adjustment and GLD +0.804, while other symbols averaged zero. Several top headlines appear to describe duplicate underlying Hormuz or Saudi supply events. Hypothesis: duplicate-event concentration may overstate geo evidence, but the supplied data do not establish the deduplication behavior or outcome impact.
- Observed: Premarket intelligence produced five BULLISH snapshots with score 75, small positive SPY and QQQ gaps, and RISK_ON regime. Social sentiment was explicitly unavailable. Dashboard signals showed zero premarket adjustment later in the day, consistent with an expired active window, but no opening-window outcome ledger was supplied.
- Observed: Financial-leverage SHADOW was enabled but produced zero snapshots, signals, and outcomes. XLF, FAS, and FAZ premarket gaps were also null. Consequently, there is no evidence to assess the configured score floor of 70 or any leveraged-financial candidate behavior.
- Observed: ZPTA SHADOW model/horizon cells have only 7 or 8 samples, below the minimum calibration target of 12. Continuation, pullback, and VWAP-reclaim results were weak in these tiny samples, while no shadow trades closed. The latest provider was yahoo_delayed and the latest status was NO_NEW_BAR, so threshold changes would be premature.
- Evidence gap: Forward returns are not supplied for ordinary threshold crossings, rejected candidates, regime decisions, VIX adjustments, geo adjustments, or premarket bias. This prevents attribution of outcomes to individual model components.

### Per-symbol paper P/L

- AAPL: 1 completed, $-2.25

### Current proposal count

- 5 proposal(s) drafted for human review.
