# StockTracker Performance — Latest

Review date: **2026-10-08**
Generated: 2026-10-08T20:05:04.105784+00:00

## Paper-trading results

- Decisions: **3150**
- Orders: **3** (buys 1 / sells 2)
- Completed paper trades: **2**
- Realized paper P/L: **$+84.98**
- Win/loss: **2/0**
- Win rate: **100.0%**

## Review

The paper system was operational and profitable on the limited realized sample, but today does not support execution-threshold or exit-setting changes. Of 3,150 decisions, 3,147 were HOLD, one was BUY, and two were SELL. Three order attempts were accepted and all had corresponding orders and fills; only the two closing sells produced realized records, totaling +$84.98. The open TSLA fill must not be counted as realized performance. Several symbols exceeded the 70 BUY threshold without a BUY, but event-level gate and forward-return evidence is insufficient to determine whether these were harmful misses. Critical SHADOW datasets for premarket and XLF/FAS/FAZ leverage research were empty, regime observations had no state variation, and all per-model ZPTA samples were below the 12-sample calibration minimum. Preserve paper=True, portfolio and loss caps, current thresholds, and read-only dashboard behavior.

Data quality: **LIMITED**

### Supporting evidence

- Published files: **20**
- Published rows analyzed: **3374**
- Integrity status: **PASS**
- Integrity issues: **none**

### Findings
- Observed integrity: supporting_log_analysis reports PASS with no listed integrity issues, no database error, and all 3,374 published rows analyzed across 15 row-bearing/recognized tables. There were no duplicate decision IDs, orphan order attempts, accepted attempts missing order IDs, duplicate fill order IDs, or resolved ZPTA predictions missing returns.
- Coverage gaps remain material despite the PASS: financial_leverage_shadow, financial_leverage_signals, financial_leverage_outcomes, premarket_intelligence, and zpta_shadow_trades were empty. Consequently there is no same-day XLF/FAS/FAZ signal or forward-outcome evidence, no premarket gap/bias evidence, and no ZPTA shadow-trade P/L or exit-reason evidence.
- The funnel recorded eight rows: five AWAITING_CONFIRMATION and three ORDER_ACCEPTED. It also reports six raw threshold crossings while side counts total eight events (five BUY and three SELL); this semantic mismatch needs reconciliation even though referential integrity passed. Published order-gate counts contain only three ORDER_ACCEPTED events because awaiting-confirmation events never became order attempts.
- Order lifecycle distinctions: requested/submitted order notionals were one $2,500 TSLA BUY and SELL notionals of $2,576.04 for AAPL and $2,511.91 for SPY. There were three accepted attempts, three orders, and three fills, but only two realized closing records. Realized P/L was +$84.98 from AAPL (+$75.25) and SPY (+$9.73); TSLA remained open and therefore contributed no realized P/L.
- The 100% win rate is based on only two realized exits and is not calibration evidence. The dashboard snapshot showed approximately +$58.27 aggregate unrealized P/L across XOM and TSLA, but this is a point-in-time snapshot, not realized performance. Portfolio return percentage and drawdown cannot be computed because starting equity and intraday equity-curve data were not supplied. The 1% objective therefore cannot be evaluated and remains only a stretch research benchmark.
- Buy/sell balance was sparse but operationally balanced at the order level: one accepted BUY and two accepted SELLs. Only one of 3,150 decision rows was a BUY and two were SELLs; 99.90% were HOLD. This alone does not establish excessive restrictiveness because repeated minute-level rows are not independent opportunities.
- Threshold opportunity evidence: AAPL reached 74.410, GLD 73.207, NVDA 71.235, TSLA 71.557, and XOM 78.240, while only TSLA generated a BUY. The funnel indicates that confirmation blocked five candidate events overall, but supplied aggregates do not map each blocked event to a symbol and timestamp. XOM and possibly AAPL also had position-state complications, so their threshold peaks cannot safely be labeled missed entries.
- Explicit missed-opportunity candidates: NVDA produced no BUY despite a maximum score of 71.235; GLD produced no BUY despite 73.207. Confirmation is the likely aggregate blocker, but exact attribution is unavailable. Required evidence is event-level symbol, timestamp, raw score, confirmation counter, position state, gate reason, price/volume features, and 5/15/30/60-minute forward returns.
- QQQ showed strong late-session relative volume of 5.157 and positive 5/15-minute momentum, but its daily maximum score was only 68.711, below the 70 threshold, so the score gate prevented entry at its best observed score. Forward outcomes after the high-volume episode are absent, so lowering the threshold is not justified.
- NVDA's closing snapshot had elevated volume ratio 3.165 but flat-to-negative short momentum and score 42.38, so the closing observation itself was not a missed momentum entry. Its earlier 71.235 peak needs timestamped feature and forward-return evidence. TSLA was captured with a BUY; NBIS was not in the configured universe and has no evidence.
- The static score-plus-two-confirmation framework may be restrictive for episodically volatile names because NVDA crossed 70 without a BUY and five funnel events awaited confirmation. However, TSLA was captured and no missed-event forward outcomes were published. There is insufficient causal evidence to loosen thresholds or confirmations for NVDA, TSLA, or any unobserved NBIS case.
- Per-symbol capture differed materially: TSLA generated the only BUY; AAPL and SPY generated the two SELLs; AMZN, QQQ, WMT, NVDA, GLD, and XOM generated no new BUY. AMZN, QQQ, SPY, and WMT never reached 70, while NVDA and GLD did. XOM's average score of 58.226 was highest, largely because its average geo adjustment was +7.754 versus average technical score 50.671.
- Geo data materially influenced XOM and modestly influenced GLD: average geo adjustments were +7.754 and +1.939 respectively, while all other symbols were zero. The feed had 181 active events and repeated versions of the same Guardian headline among top events. This raises a hypothesis of duplicate-headline amplification, but no event-level deduplication or counterfactual score/outcome evidence was supplied.
- Geo feed health is not clean: the last 500 log lines contained 14 errors and 34 warnings. The feed still reported status ok and continued updating, but error categories and impact on scoring were not provided.
- VIX effects were negligible today: average symbol adjustments ranged roughly from -0.012 to +0.004, with VIX near 15.57. There is no evidence that VIX materially changed opportunity capture or realized P/L.
- Market-regime SHADOW evidence was unanimous RISK_ON across 70 snapshots with score 100, and all five linked shadow decisions were ALLOW_EQUITY. This confirms internal consistency for today's benign state but supplies no contrasting regime observations and cannot support calibration or promotion into execution logic.
- Financial-leverage SHADOW was enabled but produced no XLF/FAS/FAZ snapshots, signals, or outcomes; the dashboard explicitly reported FINANCIAL_SNAPSHOT_UNAVAILABLE. No conclusion about leveraged-financial signal quality is possible.
- Premarket intelligence was enabled but produced zero rows, zero gap measurements, and no bias, regime, geo-status, or source-status record. Social sentiment remains unavailable because premarket_social_source is explicitly UNAVAILABLE.
- ZPTA produced 120 predictions and 92 resolved predictions, but each reported model/horizon has only 7 or 8 samples, below the minimum calibration target of 12. Zero shadow trades and no exit reasons were recorded. Identical average returns across several model families at each horizon suggest shared outcome labels rather than independently demonstrated model value; this is an instrumentation question, not evidence for tuning.
- Fixed 2% stop, 3% take-profit, 1% trailing activation, and 1.25% trailing distance cannot be assessed against symbol volatility because ATR, realized volatility, maximum adverse excursion, and maximum favorable excursion were not supplied. No execution change is supported.

### Per-symbol paper P/L

- AAPL: 1 completed, $+75.25
- SPY: 1 completed, $+9.73

### Current proposal count

- 6 proposal(s) drafted for human review.
