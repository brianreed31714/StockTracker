# StockTracker Performance — Latest

Review date: **2026-09-25**
Generated: 2026-09-28T03:23:08.241842+00:00

## Paper-trading results

- Decisions: **4156**
- Orders: **0** (buys 0 / sells 0)
- Completed paper trades: **0**
- Realized paper P/L: **$+0.00**
- Win/loss: **0/0**
- Win rate: **n/a%**

## Review

Decision coverage is substantial, but execution and outcome evidence is absent. The model produced 4,154 HOLD and 2 BUY decisions, with both BUY actions in TSLA, yet no orders, fills, trade rows, or realized trades were recorded. Score extrema crossed configured thresholds for several symbols, but the supplied aggregates cannot show crossing frequency, confirmation persistence, position eligibility, or blocking reasons. The dashboard and geo snapshots are not aligned to the 2026-09-25 review date, limiting causal interpretation. No threshold, VIX, geo, or exit calibration is supported today.

Data quality: **LIMITED**

### Findings
- Observed: 4,154 of 4,156 decisions were HOLD (99.952%); 2 were BUY (0.048%), both for TSLA. There were no SELL decisions.
- Observed: TSLA's action-level BUY rate was 2 of 461 rows (0.434%). Every other symbol had zero BUY and SELL actions.
- Observed: AMZN, NVDA, and TSLA had maximum scores above the 70 buy threshold. NVDA, TSLA, and XOM had minimum scores below the 30 sell threshold. Aggregate extrema do not reveal the number or duration of threshold crossings, and therefore do not establish whether the two-confirmation requirement was met.
- Observed: No orders, fills, trade CSV rows, or realized-trade rows were recorded. Realized P/L of zero reflects the absence of realized records and is not evidence of flat model performance.
- Observed: The two TSLA BUY decisions did not become recorded orders. Hypothesis: they may have been blocked by confirmation, portfolio, session, duplicate-order, or other eligibility controls, but no rejection-reason evidence is supplied.
- Observed: Average scores varied moderately by symbol, from 47.825 for AMZN to 51.865 for TSLA. One day without executions or forward-return labels cannot support per-symbol threshold changes.
- Observed: Average VIX adjustments ranged from -0.176 for GLD to +0.500 for TSLA. The only supplied VIX level, 14.87, comes from a dashboard generated after the review date, so VIX effects cannot be linked reliably to the 2026-09-25 decisions.
- Observed: Average geo adjustment was 0.0 for every symbol, including XOM, while the available geo artifact reported a +7.1 adjustment. That artifact was generated on 2026-09-19, six days before the review date, and contains apparent duplicate coverage of the same headlines across domain variants.
- Observed: The geo feed's average model contribution cannot be evaluated from this day because no decision row shows a nonzero geo adjustment. Hypothesis: a freshness or applicability gate may have correctly suppressed the stale artifact, but the supplied data does not identify the reason.
- Observed: The dashboard snapshot was generated on 2026-09-27 rather than the 2026-09-25 review date. It showed 5 open positions and $12,575.46 exposure versus configured caps of 4 positions and $10,000. Because of the date mismatch and possible market-value appreciation, this does not prove that a same-day order breached a cap.
- Observed: The later dashboard's five positions had market values slightly above $2,500 each. This alone does not prove violation of the $2,500 entry-notional limit because market values can rise after entry.
- Observed: Buy/sell balance, realized profitability, stop-loss behavior, take-profit behavior, and trailing-stop behavior cannot be assessed without orders, fills, exits, and time-aligned position history.

### Per-symbol paper P/L

- No completed trades for this review date.

### Current proposal count

- 5 proposal(s) drafted for human review.
