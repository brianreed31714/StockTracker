# ZPTA Bottom Hunter — October 26, 2026: first prospective daily-low candidate and source discrepancy

**Decision: NOT READY FOR REAL-MONEY TRADING.** New completed-day technical candidate exists, but the research feed's volume disagrees materially with an independent daily source. Do not interpret the intraday low as a buyable price, and do not retroactively optimize the previously examined holdout. No execution code, broker settings, risk limits or paper/shadow isolation were changed.

## 1. Actual October 26 completed-day price action

S&P Global Market Intelligence via Stock Analysis (updated Oct 26) displays:
- OPEN **$0.75**, HIGH **$0.75**, LOW **$0.63** (rounded display), CLOSE **$0.72**, VOLUME **279,654** shares.
- Investing.com's Oct 26 history independently displays OPEN **$0.75**, HIGH **$0.75**, LOW **$0.631**, CLOSE **$0.72**, VOLUME **279.65K**.
- Close vs Friday Oct 23 close $0.75: **-4.00%**.
- Oct 26 low vs Friday close: approximately **-15.87%** using $0.631.
- Oct 26 low-to-close recovery: approximately **+14.10%** using $0.631. **This is a SAME-DAY rebound, not a demonstrated 1/3/5-day future recovery, and is not an assumed executable entry.**
- S&P daily close×volume proxy: **$201,350.88**, not order-book depth.
- Historical last ten sessions' highest reported high (through Oct 23) **$0.8022**; Oct 26 close is **10.25% below** that high.

Public evidence:
- https://stockanalysis.com/quote/otc/ZPTA/history/ (S&P Global Market Intelligence, Oct 26 EOD)
- https://cn.investing.com/equities/andretti-acquisition-historical-data (Oct 26 row; low $0.631)
- https://twelvedata.com/markets/939465/stock/otc/zpta/historical-data (earlier precise Oct 12–23 bars)

## 2. Frozen preregistered signal interpretation

The **existing** October 22 ruleset `ZPTA_DAILY_V1_FROZEN_2026_10_22` returns **one candidate condition** on the completed Oct 26 bar:

`down_day_10pct_below_prior_ten_day_high`

The other four predefined signals do **not** trigger: Oct 26's close-to-close drop is only 4% (not >=5%); Friday was an up day, so this is not two consecutive down closes; three-session RSI is about **37.5** (not <=25); and the close did not rise from the prior session to confirm a reversal.

The new `analysis/zpta_prospective_daily_snapshot.py` generates date-fresh, post-close-only research snapshots, hashes source OHLCV, retains original signal flags, and leaves 1/3/5-session future outcomes **NULL**. No entry was placed, and the source candidate is **not** an approved buy signal. If tomorrow's open or spread is poor, the research does not assume a fill at today's low.

Future hypothetical print-price outcomes for the Oct 26 candidate cannot be known until the Oct 27 (1-session), Oct 29 (3-session), and Nov 2 (5-session) closes. One candidate cannot establish predictive accuracy.

## 3. MATERIAL NEW DATA-QUALITY FINDING: 75.69% volume disagreement

The Oct 26 GitHub Actions Yahoo daily fetch at **2026-10-27T00:57:22Z** returned **500** rolling 2-year bars, Oct 28 2024–Oct 26 2026 (five zero-volume days, no reported split events). Its last close matched S&P at approximately **$0.72**, but Yahoo's same-day **67,987 shares** differed from S&P's **279,654 shares**:

| Oct 26 provider | Close | Reported volume | Close×volume proxy |
|---|---:|---:|---:|
| Yahoo chart endpoint (GitHub fetch 5:57 PM Pacific) | $0.72 | **67,987** | **$48,950.64** |
| S&P Global Market Intelligence (Stock Analysis) | $0.72 | **279,654** | **$201,350.88** |
| Relative discrepancy vs S&P | ~0% | **75.69%** | **75.69%** |

Both printed turnover proxies exceed the research $25k floor, but this does **not** make the market data verified. Oct 23 Yahoo volume was also revised between initial and later retrievals. The reason for the Oct 26 difference is not established (publication delay, partial volume or venue coverage are hypotheses). Never select the more favorable value or revise a frozen prediction silently.

The first same-day candidate log recorded:
- Source hash: `5e46d166963d425c1b60b22be8697e7abcf8b3518cb8052df5bf9c7190a2ad8d`.
- `snapshot_type=SAME_DAY_POST_CLOSE_CANDIDATE`, `candidate_status=RESEARCH_CANDIDATE_UNVERIFIED`.
- `future_outcomes={1d:null,3d:null,5d:null}`; `real_money_trading_allowed=false`.
- GitHub Actions run: https://github.com/brianreed31714/StockTracker/actions/runs/40429621067

A later revision of the candidate Yahoo source must be flagged as a revision, not silently substituted. The input hash locks what the first research engine saw; it is not proof of source truth.

Added `analysis/zpta_cross_provider_anchor.py` and tests to fail the source-quality check when independently published daily volume or close diverges materially. Added `analysis/zpta_prospective_outcome_score.py` to score only subsequently completed 1/3/5-session bars and reject changes to the original signal-day close or volume. The GitHub workflow now preserves **derived snapshot JSON only** as a 90-day artifact; it does not upload raw licensed historical OHLCV.

## 4. Previous risk evidence remains binding

Do not treat this one new candidate as evidence of improved strategy profitability. The already-examined OTCQB-only five-session >=5% down-close simulation had 11 independent hypothetical positions, +4.99% capped sleeve return, and **-15.87% close-mark max drawdown**—above the <=8% risk target. The new Oct 26 candidate is a different rule (prior-10-day drawdown), not the >=5% down-close signal. No new 1/3/5-day forward outcome exists yet.

The current daily dataset still lacks independently certified full historical split-adjustment and executable OTC bid/ask/size data. The October 9 shareholder reverse-split **authorization** is not confirmation of implementation. Public 8-K: https://www.stocktitan.net/sec-filings/ZPTA/8-k-zapata-quantum-inc-reports-material-event-64f1fcb03607.html

## 5. Engineering, CI and next steps

This run adds research-only prospective snapshot, cross-provider discrepancy, forward outcome scoring, deterministic tests, and CI artifact retention to draft PR #6. The initial 68-test CI attempt found one **test fixture** issue (stale-data fixture had fewer than eleven lookback bars), which was corrected without relaxing the stale-data gate. **Final CI checks for the latest head must be independently verified before any merge; do not claim success from a passing candidate-data job alone.**

Next: (a) independently reconcile Oct 26 volume and detect any Yahoo revisions, (b) preserve the dated signal and score its future outcomes without changing the original rule or signal timestamp, (c) continue venue-appropriate OTCQB-only matched baselines, cost and drawdown stress, and (d) confirm corporate-action and broker execution data before any live-readiness promotion. The $8 IBKR subscription is **not** needed just for this daily historical research.

**November 2 remains a conditional review, not an automatic live launch. PAPER_ONLY / ZPTA SHADOW_ONLY unchanged.**
