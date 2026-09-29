# StockTracker Performance — Latest

Review date: **2026-09-29**
Generated: 2026-09-29T20:30:03.758958+00:00

## Paper-trading results

- Decisions: **3333**
- Orders: **2** (buys 1 / sells 1)
- Completed paper trades: **1**
- Realized paper P/L: **$-54.95**
- Win/loss: **0/1**
- Win rate: **0.0%**

## Review

The paper system operated within all stated risk limits, but same-day evidence is insufficient for model calibration. It generated 3,333 decisions but only two paper orders and one realized exit, so the -$54.95 realized result cannot support threshold, confirmation, exit, symbol, VIX, geo, or regime changes. The clearest opportunities are SHADOW instrumentation and data-pipeline repairs: reconcile threshold-funnel accounting, capture counterfactual forward outcomes, restore the financial-leverage feed, audit geo attribution/deduplication, and improve premarket/ZPTA observability. Keep paper=True and leave all trading thresholds, portfolio caps, loss controls, and dashboard permissions unchanged.

Data quality: **LIMITED**

### Findings
- Observed: PAPER-only status is confirmed. Three open positions and approximately $7,475.30 exposure remained below the caps of four positions and $10,000. Two trades remained below the 12-trade limit, and realized P/L of -$54.95 remained above the -$300 daily-loss stop. The $2,500 XOM order was at, not above, the per-trade cap.
- Observed: Decision activity was extremely sparse: 3,331 HOLD, one BUY, and one SELL across 3,333 rows. The two accepted paper orders were balanced by side: one XOM buy and one NVDA sell.
- Observed: Only one realized trade is available. NVDA realized -$54.95; this sample is too small to estimate win rate, symbol quality, exit quality, or expected P/L.
- Observed: AMZN reached 70.499 and XOM reached 71.963, while WMT reached 26.528 and XOM reached 29.492. However, only XOM produced a buy and only NVDA produced a sell. Confirmation state, position eligibility, and exact crossing disposition are not fully represented in the aggregate symbol table.
- Observed: Funnel telemetry reports three raw threshold crossings, but four funnel rows split into two BUY and two SELL records. Two awaited confirmation and two were submitted. This may reflect different counting definitions, but the supplied evidence does not permit reconciliation.
- Observed: All two order attempts were accepted, with no pre-submit blocks or submission failures. There is no same-day evidence of an execution reliability problem.
- Observed: Average VIX adjustments were small by symbol, ranging from -0.018 to +0.006, while individual dashboard adjustments ranged from approximately -0.587 to +0.205. With one realized trade, no causal conclusion about VIX adjustment quality is supported.
- Observed: Geo data was live and contributed mainly to XOM and GLD. XOM's average geo adjustment was -0.372 and its displayed adjustment was -0.51, although several highest-materiality headlines were classified as bullish for crude and often bullish for XOM. The overall feed signal was negative, so this is an attribution question rather than proof of a sign error.
- Observed: The geo top-event list contains apparent duplicates differing primarily by source capitalization. Duplicate amplification could affect the aggregate signal, but its actual score impact is not provided.
- Observed: Regime SHADOW produced 75 RISK_ON observations at score 85, with no state variation. Only two regime-decision records were present, both ALLOW_EQUITY for XOM. This supports pipeline availability but not regime effectiveness.
- Observed: Financial-leverage SHADOW produced zero snapshots, signals, or outcomes, and the dashboard reported FINANCIAL_SNAPSHOT_UNAVAILABLE. XLF, FAS, and FAZ premarket gaps were also null. No financial-leverage conclusion is possible.
- Observed: Premarket intelligence produced five NEUTRAL snapshots. SPY and QQQ gaps were small and positive, social sentiment was explicitly unavailable, and no evidence links the premarket bias to later outcomes. Social sentiment must therefore remain excluded.
- Observed: ZPTA has 56 resolved predictions overall, but every reported model/horizon cell has only four or five samples, below the minimum calibration target of 12. It generated no shadow trades, used yahoo_delayed, and ended with NO_NEW_BAR. No ZPTA threshold or model ranking change is supported.
- Hypothesis: Sparse actions may be an intended consequence of 70/30 thresholds plus two confirmations, but the present telemetry cannot distinguish desirable selectivity from missed or inconsistently counted opportunities.
- Hypothesis: Geo duplicate handling or aggregation across market-risk and XOM-specific effects may explain the negative XOM adjustment despite bullish oil headlines. A sign defect is possible but not established.
- Hypothesis: Missing financial snapshots and stale delayed ZPTA bars are instrumentation/data-availability issues rather than evidence that the underlying shadow strategies lack signal.

### Per-symbol paper P/L

- NVDA: 1 completed, $-54.95

### Current proposal count

- 6 proposal(s) drafted for human review.
