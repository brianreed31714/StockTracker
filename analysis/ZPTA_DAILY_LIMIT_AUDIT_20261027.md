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

## Material October 27 cross-provider disagreement (checked after initial checkpoint)

A new GitHub Actions research fetch (run **40612642610**, Oct 27 session, 2026-10-28T01:03Z) produced 501 candidate daily rows, ending **October 27**. Its frozen post-close research candidate was **NO_QUALIFYING_RESEARCH_ENTRY**: Yahoo close **$0.74**, low **$0.69**, volume **14,491**, 2.7778% daily close gain, RSI(3) **62.5**, no frozen entry flags, and close×volume **$10,723.34** (below the $25k research floor). The snapshot's source hash was `a2738e65ad434bbc2b8a77b716b915a1287c2e48232721e81398f39222f30c67`. All 1/3/5-session future outcomes remain NULL.

**Independent source conflict:** S&P Global Market Intelligence, published via Stock Analysis's October 27 historical row, reported close **$0.73**, low **$0.69**, volume **35,982**. That is a **1.37% closing-price disagreement** and **59.73% volume disagreement** relative to S&P. S&P's close×volume proxy is **$26,266.86**, *above* the $25k floor. This is a **material liquidity-gate classification disagreement**; the source must be labelled `SOURCE_MISMATCH_DO_NOT_PROMOTE` and not treated as a verified entry or validated forward return. Both feeds show no obvious preregistered technical flag from the available close-based checks, but this is not proof of execution feasibility.

Source: https://stockanalysis.com/quote/otc/ZPTA/history/ (S&P Global Market Intelligence, updated October 27). GitHub Actions: https://github.com/brianreed31714/StockTracker/actions/runs/40612642610 . Publication timing or venue coverage could explain some differences; no cause has been established. Do not silently replace the frozen Yahoo observation with S&P or select whichever makes the trade look more favorable.

**Why the one-cent disagreement matters:** Using S&P's published October 27 opening print of $0.72, a hypothetical purchase at that open and sale at S&P's $0.73 close would return **-0.62%** after 1% assumed friction each way. If one *assumed* the same opening print but substituted Yahoo's $0.74 close, the hypothetical result would instead be **+0.74%**. The latter is only a sensitivity illustration (Yahoo's actual open is not established here), **not** a valid scored outcome. One cent can reverse the sign of a penny-stock backtest; neither calculation proves an executable fill. Because the frozen October 26 bar itself has unresolved volume revisions, the prospective scorer must remain fail-closed.

**CI evidence:** The new next-session limit tests were included in the 91 offline ZPTA deterministic tests that passed on code SHA `9661cacf38ffa8152d943fcdfe88cffca65f1221`; the data-research job on that SHA also passed. This validates the tests and scripted research mechanics, **not** historical price truth, broker fills, or Windows activation. Required checks on the final documentation head must be verified separately before merge.

## Validation and next steps

- New tests cover signal-day no-lookahead, no touch-only fills, pending forward outcomes, fees, duplicate dates, invalid settings, volume gating and explicit paper-only limitations.
- GitHub Actions CI must independently run and pass on the new head SHA before any PR can be merged. A code commit is not CI evidence.
- Reconcile the **materially conflicting** October 27 S&P and Yahoo close/volume, and the October 26 source revision, before promoting or scoring forward outcomes; verify corporate actions against issuer/exchange history.
- Continue prospective daily signals and fresh post-freeze 1/3/5-session outcome scoring; do not retrofit the previously examined holdout. Track liquidity, non-overlap, drawdown and realistic OTC execution costs.
- PR #14 is a separate approved missed-rebound/blocked-opportunity track; avoid duplicating work or promoting the current intraday-only shadow specialist to a multi-day execution strategy.

**Operational boundary:** Existing ZPTA shadow-only settings, Windows processes, risk limits, Pushover and deployment agents unchanged. November 2 is a conditional go/no-go, not an automatic activation.
