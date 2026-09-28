# StockTracker Performance — Latest

Review date: **2026-09-28**
Generated: 2026-09-28T20:30:03.398855+00:00

## Paper-trading results

- Decisions: **3325**
- Orders: **4** (buys 1 / sells 3)
- Completed paper trades: **3**
- Realized paper P/L: **$+87.73**
- Win/loss: **2/1**
- Win rate: **66.67%**

## Review

Same-day operations were healthy and remained paper-only: 3,325 decisions produced 4 accepted orders with no submission failures, while portfolio and daily-loss controls remained intact. Realized paper P/L was +$87.73 across only 3 exits, which is far too small for performance or threshold calibration. Signal activity was sparse, financial-leverage SHADOW data was entirely unavailable, regime evidence covered only RISK_ON, and premarket evidence contained only 5 bearish snapshots. No production threshold, confirmation, risk-cap, or execution-policy change is supported today.

Data quality: **LIMITED**

### Findings
- Observed: 3,319 of 3,325 decisions were HOLD; only 3 BUY and 3 SELL decisions occurred. The funnel recorded 13 raw threshold crossings, with 9 events awaiting confirmation and 2 blocked by MAX_OPEN_POSITIONS.
- Observed: The funnel was buy-heavy at 11 BUY-side versus 4 SELL-side events, but submitted orders were 1 buy and 3 sells. This difference cannot be evaluated causally from the supplied same-day data.
- Observed: All 4 attempted submissions were accepted, with zero submit failures. Two additional attempts were blocked before submission by the existing maximum-open-position control, showing that the portfolio cap was active.
- Observed: Realized paper P/L was +$87.73 from 3 exits: NVDA +$101.77, AAPL +$0.17, and QQQ -$14.22. The sample is below the minimum calibration target of 12 and does not support threshold, stop, take-profit, or symbol-specific tuning.
- Observed: Per-symbol score ranges differed. NVDA and TSLA reached both unusually low scores and scores above the buy threshold; GLD also produced a BUY. AMZN peaked at 69.099 and generated no action. These are descriptive same-day facts, not evidence for per-symbol thresholds.
- Observed: VIX adjustments were negligible on average by symbol, approximately -0.005 to +0.002, with VIX near 16.12 at the dashboard snapshot. No forward-outcome attribution is supplied, so the usefulness of the VIX component is unknown.
- Observed: Geo adjustments were concentrated in XOM and GLD. XOM averaged +3.415 geo points, while its average total score was 52.278 and no XOM order occurred. The feed contained 220 active events and multiple near-duplicate Hormuz/CNBC headlines.
- Hypothesis: Duplicate or closely syndicated geo headlines may inflate event counts or adjustment persistence. The evidence does not show whether the current aggregator already deduplicates their scoring impact.
- Observed: Market-regime SHADOW produced 79 of 79 RISK_ON states and 11 of 11 ALLOW_EQUITY decisions. This confirms logging but provides no contrasting regime state with which to assess discrimination or gating value.
- Observed: Financial-leverage SHADOW produced zero XLF/FAS/FAZ snapshots, signals, or outcomes. Premarket XLF/FAS/FAZ gaps were also null, and the dashboard reported FINANCIAL_SNAPSHOT_UNAVAILABLE. No conclusion about these signals is possible.
- Observed: All 5 premarket snapshots were BEARISH, with the latest SPY and QQQ gaps at -0.342% and -0.523%. The regular-session dashboard showed a zero premarket adjustment, consistent with either expiry or non-application, but the supplied evidence does not establish which path occurred or whether the bias was predictive.
- Observed: Social sentiment was explicitly UNAVAILABLE; it must not be treated as an input or used to explain any decision.
- Observed: At the dashboard snapshot, 3 positions used about $7,414.96 of exposure and had approximately -$62.81 combined unrealized P/L. Existing exposure, position, trade-count, and daily-loss limits were not breached.

### Per-symbol paper P/L

- AAPL: 1 completed, $+0.17
- NVDA: 1 completed, $+101.77
- QQQ: 1 completed, $-14.22

### Current proposal count

- 5 proposal(s) drafted for human review.
