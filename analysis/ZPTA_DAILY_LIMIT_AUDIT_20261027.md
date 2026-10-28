# ZPTA daily-low research checkpoint — 2026-10-27

**Research status: NOT READY FOR REAL-MONEY TRADING.** User has approved enhancements #1–#18, including StockTracker #1–#9 (issue #15); this checkpoint stays within already approved research scope. PR #6 and PR #14 remain draft; nothing was merged or deployed.

## What is verified in repository

- Frozen October 26 research snapshot is dated, source-hashed and marked `RESEARCH_CANDIDATE_UNVERIFIED`. Its sole technical flag is `down_day_10pct_below_prior_ten_day_high`; 1-, 3- and 5-session future outcomes were NULL when frozen. This is **not** a buy order.
- October 26's published closing price was $0.72, after an approximately $0.631–$0.6346 intraday low. Its low-to-close recovery is **same-session hindsight**, not a next-day or five-day predicted rebound.
- The October 26 Yahoo source volume was 67,987 while the independent S&P published volume was 279,654; the 75.69% disagreement is unresolved. No revised data may silently overwrite the frozen input.
- Prior OTCQB-era, already examined historical results for the same prior-ten-day-high drawdown rule were negative at 1 and 3 sessions, and near flat at 5 sessions. Those results are not new holdout evidence.
- No verified October 27 completed-day, independently reconciled OHLCV was available from the checked public historical pages at this checkpoint. Do **not** assert a new October 27 candidate or score October 26's first forward outcome without a settled bar and source-revision reconciliation.

## New research implementation (PR #6)

Added `analysis/zpta_next_session_limit_audit.py` and `tests/test_zpta_next_session_limit_audit.py` (ten deterministic test cases). The module uses **only completed signal-day bars** to precommit a conservative hypothetical buy limit, comparing a 3% discount and the lowest of the last five *already completed* lows. It evaluates only the five previously frozen signals; no indicator selection was optimized on the examined holdout.

For the next session, each limit is classified as:

- `OPEN_PRINT_ELIGIBLE_UNVERIFIED`: next session's published opening print at or below the precommitted limit; hypothetical scenario only, **not a broker fill**.
- `INTRADAY_TOUCH_NO_FILL_ASSUMED`: daily low touches limit but opening print does not; **not counted as a filled trade**.
- `LIMIT_NOT_REACHED`: no apparent opportunity at that limit.
- `PENDING_NEXT_SESSION`: no completed next session; no future result may be scored.

Only open-print scenarios receive hypothetical 1/3/5-session close exits, with 1% default one-way cost, worst holding-window low, matched same-date next-open baseline, chronological 70/30 embargo and non-overlapping per-horizon counts. These are descriptive scenarios, not execution-feasibility claims. The already examined holdout is explicitly labelled as such, never called a fresh validation period.

The source dataset remains **not independently split-adjustment verified**; neither executable bid/ask, venue entitlements nor fill probability is established. No intraday-touch or day's-low hindsight fills are claimed.

## Validation and next steps

- New tests cover signal-day no-lookahead, no touch-only fills, pending forward outcomes, fees, duplicate dates, invalid settings, volume gating and explicit paper-only limitations.
- GitHub Actions CI must independently run and pass on the new head SHA before any PR can be merged. A code commit is not CI evidence.
- Obtain a settled October 27 bar from independent sources, resolve source revision of October 26 volume before scoring its forward outcome, and verify corporate actions against issuer/exchange history.
- Continue prospective daily signals and fresh post-freeze 1/3/5-session outcome scoring; do not retrofit the previously examined holdout. Track liquidity, non-overlap, drawdown and realistic OTC execution costs.
- PR #14 is a separate approved missed-rebound/blocked-opportunity track; avoid duplicating work or promoting the current intraday-only shadow specialist to a multi-day execution strategy.

**Operational boundary:** Existing ZPTA shadow-only settings, Windows processes, risk limits, Pushover and deployment agents unchanged. November 2 is a conditional go/no-go, not an automatic activation.
