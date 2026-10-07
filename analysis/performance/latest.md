# StockTracker Performance — Latest

Review date: **2026-10-07**
Generated: 2026-10-07T20:05:03.874407+00:00

## Paper-trading results

- Decisions: **3150**
- Orders: **2** (buys 1 / sells 1)
- Completed paper trades: **1**
- Realized paper P/L: **$+39.41**
- Win/loss: **1/0**
- Win rate: **100.0%**

## Review

The paper system was operational and internally consistent, but evidence is limited to one session with one realized trade. Across 3,150 decisions, only three raw threshold crossings produced one BUY and one SELL; both submitted orders were accepted and filled. XOM generated the only realized paper result, +$39.41, while no drawdown series was supplied. TSLA and NVDA showed the clearest no-position momentum/volume snapshots but never reached the 70 BUY threshold; AMZN reached 72.697 yet produced no BUY, with aggregate funnel evidence pointing to confirmation as the blocker. This suggests the static framework may under-capture volatile symbols, but forward outcomes are missing, so no execution-threshold change is justified. Keep paper=True, portfolio and loss caps, and the read-only dashboard unchanged.

Data quality: **LIMITED**

### Supporting evidence

- Published files: **20**
- Published rows analyzed: **3558**
- Integrity status: **PASS**
- Integrity issues: **none**

### Findings
- Observed integrity: supporting_log_analysis passed with no listed integrity issues, no database error, and all 3,558 published rows reported analyzed across 15 tabular datasets. It found zero duplicate decision IDs, orphan attempts, accepted attempts lacking order IDs, duplicate fill order IDs, or resolved ZPTA predictions lacking returns.
- Observed evidence gaps: five published tables were empty—financial_leverage_shadow, financial_leverage_signals, financial_leverage_outcomes, premarket_intelligence, and zpta_shadow_trades. Thus enabled XLF/FAS/FAZ research, premarket gap/bias research, and ZPTA trade outcomes cannot be evaluated. Social sentiment was explicitly unavailable and must not be assumed.
- Observed funnel: 3,150 decisions consisted of 3,148 HOLD, one BUY, and one SELL. There were only three raw threshold crossings, approximately 0.095% of decision rows, although row-level and event-level denominators are not necessarily interchangeable. Funnel gates were two ORDER_ACCEPTED and two AWAITING_CONFIRMATION; both actual order attempts were accepted, so there is no evidence of portfolio-cap, daily-loss, or broker-submit rejection.
- Observed opportunity capture: XOM reached 79.348 and generated both the sole BUY and sole SELL. AMZN reached 72.697 but generated no BUY. Aggregate evidence records two BUY-side AWAITING_CONFIRMATION events and regime shadow includes AMZN, making confirmation the likely AMZN blocker, but the supplied summary does not provide the event-level symbol/gate join needed for definitive attribution.
- Observed missed opportunities: TSLA had a no-position snapshot with +0.241% 15-minute momentum, 3.54 volume ratio, and score 64.83; its full-day maximum was 68.13. NVDA had +0.141% 15-minute momentum, 2.86 volume ratio, and score 60.93; its maximum was 68.65. Neither reached the 70 threshold, and both snapshot reasons showed buy confirmation 0/2. Forward MFE/MAE after their score peaks is absent, so they cannot yet be classified as profitable missed trades.
- Observed comparison: AMZN and XOM were the only symbols whose reported daily maxima exceeded 70, while AAPL, GLD, NVDA, QQQ, SPY, TSLA, and WMT remained below it. TSLA and NVDA came within 1.87 and 1.35 points, respectively. The framework may be restrictive for volatile names, but this is a hypothesis pending forward outcomes. NBIS was not configured and has no same-day evidence, so no NBIS conclusion is possible.
- Observed order accounting: the logs show requested/order notionals of $2,500 for the XOM buy and $2,540.33 for the XOM sell, two accepted attempts, two order records, and two fills. These are distinct from the single realized P/L record of +$39.41 and from the dashboard snapshot showing three open positions and $7,567.73 exposure. The AAPL and SPY dashboard positions are not explained by same-day order rows and should not be treated as same-day entries.
- Observed performance: realized paper P/L was +$39.41 from one winning XOM realization. One trade cannot support a win-rate conclusion, stop calibration, or comparison with the 1% daily stretch benchmark. No equity curve, daily return denominator, maximum drawdown, or intraday drawdown was supplied.
- Observed context effects: VIX was 15 and falling, while average VIX score adjustments were small, ranging from -0.023 for GLD to +0.065 for NVDA and TSLA. There is no same-day variation sufficient to estimate a causal VIX effect.
- Observed regime shadow: all 70 snapshots were RISK_ON with score 100, and all three linked shadow decisions were ALLOW_EQUITY. This confirms consistent state reporting but provides no contrasting regime observations or evidence that regime filtering improves forward returns; the saturated score also limits discrimination.
- Observed geo contribution: average geo adjustment was +5.876 for XOM and +1.469 for GLD, versus zero for the other symbols. XOM's latest adjustment was about +5.39 despite the feed containing both bullish and bearish oil headlines. Geo context materially contributed to XOM's score, but no counterfactual score, event-age attribution, or forward outcome table isolates its value.
- Observed ZPTA evidence: 264 predictions were resolved and each reported horizon has at least 20 samples, but no shadow trades were opened. Multiple model families have identical sample counts, accuracies, and average returns at each horizon, which may reflect shared outcomes rather than independent model skill. Delayed Yahoo data, a LIQUIDITY_DANGER state, and no exit records further limit conclusions; no ZPTA threshold tuning is supported.
- Hypothesis on exits: fixed 2% stop, 3% take-profit, 1% trailing activation, and 1.25% trail may interact differently with TSLA/NVDA volatility than with SPY/WMT. The evidence contains no ATR, realized-range-at-entry, stop-distance normalization, or stop/target exit sample, so mismatch cannot be established from this session.

### Per-symbol paper P/L

- XOM: 1 completed, $+39.41

### Current proposal count

- 6 proposal(s) drafted for human review.
