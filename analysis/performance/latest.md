# StockTracker Performance — Latest

Review date: **2026-09-27**
Generated: 2026-09-28T03:20:40.427518+00:00

## Paper-trading results

- Decisions: **0**
- Orders: **0** (buys 0 / sells 0)
- Completed paper trades: **0**
- Realized paper P/L: **$+0.00**
- Win/loss: **0/0**
- Win rate: **n/a%**

## Review

The review is insufficient for model calibration: there were no decision, order, fill, or realized-trade records, and the daily CSV folder was absent. No threshold, confirmation, stop, take-profit, VIX, symbol-level, or geo-weight changes are supported. The main actionable issues are observability, paper-portfolio cap reconciliation, and stale/duplicated geo-feed instrumentation.

Data quality: **INSUFFICIENT**

### Findings
- Observed: The system is configured as paper-only, and no evidence supports changing that constraint.
- Observed: There were 0 decisions, 0 orders, 0 fills, and 0 realized trades. Realized paper P/L was $0, but this contains no performance information because there were no exits.
- Observed: Per-symbol behavior, threshold hit rates, buy/sell balance, win rate, and VIX effects cannot be evaluated from zero decision and trade rows.
- Observed: The daily CSV folder did not exist, although the database path and dashboard state existed. This prevents distinguishing a normal market-closed day from a collection or export failure using the daily artifacts alone.
- Observed: The dashboard snapshot reported 5 open positions and $12,575.46 exposure, exceeding the configured caps of 4 positions and $10,000 exposure. The snapshot alone does not establish when or why the excess arose.
- Observed: Position market values were approximately $2,511-$2,519 each. This does not prove violation of the $2,500 order-size cap because market appreciation can raise position value after entry.
- Observed: VIX was 14.87 in the snapshot, but there are no contemporaneous decisions or outcomes with which to measure its contribution.
- Observed: The geo artifact was generated on 2026-09-19, eight days before the review date, while still reporting status 'ok' and a +7.1 score adjustment.
- Observed: The geo top events include duplicate syndicated headlines with matching publication times and differently cased or related domains, creating a plausible risk of repeated contribution.
- Hypothesis: The cap excess may reflect pre-existing positions, configuration changes, or missing admission/reconciliation checks. The supplied evidence cannot identify the cause.
- Hypothesis: The absence of activity may be expected for a market-closed session, but the missing daily export and lack of a session heartbeat prevent confirmation.

### Per-symbol paper P/L

- No completed trades for this review date.

### Current proposal count

- 4 proposal(s) drafted for human review.
