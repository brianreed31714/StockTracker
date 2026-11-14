# ZPTA daily-swing independent-trade validation specification — 2026-11-08

Source reviewed: PR #6 immutable commit `51161184`, `analysis/ZPTA_DAILY_SWING_PLAN_20261022.md` and `analysis/zpta_daily_swing_research.py`. This is a design/evidence checkpoint, **not** a new performance result or passing CI.

## Confirmed semantics and important distinction
- Signal computed at completed close t. Entry at t+1 open; 1-session exit at t+1 close. This **is same-day open-to-close exposure on the entry day**, not a multiday rebound. 3/5-session exits occur at t+3/t+5 closes. Report 1-session and multiday outcomes separately, with overnight gap from t close to t+1 open separately.
- Existing `worst_excursion_pct` is minimum subsequent low relative to a cost-inflated next-open price; this is an **adverse price excursion proxy**, not portfolio drawdown, stop-fill proof or maximum capital drawdown.
- Existing `all_eligible_sessions` comparator is unconditional among days meeting `signal.close * signal.volume >= 25000`; it is not matched by weekday, volatility or price regime.
- `chronological_gate` and 70/30 partition purge training positions crossing cut, but do **not** select independent non-overlapping trades within a cohort. Multi-horizon averages cannot be interpreted as independent trades.
- The script reports one-way cost 1% and does not verify bid/ask, corporate-action-adjusted volume or printed opening-price executability.

## Predeclared follow-up implementation acceptance tests
1. For each signal and horizon, greedily accept a trade only when its entry index is strictly after the previous accepted exit index (one position at a time), with deterministic earliest-signal tie-breaking; compute results separately by cohort and split, never treat overlapping cohorts as independent portfolio sleeves.
2. Enforce holdout embargo at least max horizon (5 sessions), ensuring signal lookback, entry and exit boundaries cannot leak outcomes. Keep signal features calculated solely on historical completed bars.
3. Compare signal entries to deterministic matched weekday and trailing-volatility baseline entries from the same eligible period; preserve matched-sample counts and report selection failures.
4. Next-open market scenario: use printed open only as hypothetical benchmark, apply 1%/side and 2.5%/side friction sensitivity. Next-open limit scenario: precommit limit from information available at t; daily low touching limit is only a **possible fill**, never verified execution. Explicitly report zero fills when not touched and ambiguous touches separately.
5. Report mean, median, wins/trades, 95% uncertainty interval using independent trades, worst adverse excursion, peak-to-trough sequential equity drawdown and exposure; do not report percentage returns as portfolio ROI without position sizing/cash accounting.
6. Cross-check all dates and bars against corporate-action history and independently sourced precision OHLCV, including reverse-split effective dates and adjusted volume. The chat-supplied 244-session CSV is not equivalent to independently verified 501-bar history; reconcile discrepancy before model selection.
7. Run deterministic tests with synthetic cases: (a) t+1 entry and t+1 exit for 1d; (b) overlapping t+1 and t+2 signals result in only one accepted 3d trade; (c) t close to t+1 open gap is not counted as realized entry profit; (d) limit untouched => no fill; (e) low touched => uncertain fill; (f) split boundary purges crossings; (g) all baseline and holdout features timestamp-safe.

## Execution gates
No live promotion, broker order or Windows activation inferred. PR CI must pass, then host process and loaded version must be independently attested. Historical EOD work does not require a funded IBKR account. Preserve paper/shadow and existing risk limits.
