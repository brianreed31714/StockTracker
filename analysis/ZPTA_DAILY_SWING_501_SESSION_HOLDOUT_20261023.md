# ZPTA 501-session daily-low research checkpoint — 2026-10-23

**Decision: no validated positive expectancy; NOT READY for live money.** All new work is read-only research in draft PR #6. Existing StockTracker paper-only execution and ZPTA shadow isolation remain untouched. November 2 is an evidence-based go/no-go checkpoint, not automatic activation.

## Material progress: 501 historical sessions retrieved and research CI passing

The new no-credential daily history candidate fetcher ran successfully in GitHub Actions at **2026-10-23 18:08 Pacific** (2026-10-24 01:08 UTC), retrieving **501 Yahoo daily OHLCV bars from 2024-10-24 to 2026-10-23**, with **5 zero-volume days**, **0 missing OHLCV rows** in the returned payload and **no split/dividend events reported by the endpoint**. SHA256 of candidate CSV: `5a4c3d3846ffb3ed76c8ff4737504a15e3b48497fa5596e89c241b5a1b08f7c6`. CSV was ephemeral on the GitHub runner and **not published or committed**; reproducible retrieval code and provider metadata are in `analysis/zpta_daily_history_fetch.py`.

**This is NOT fully verified corporate-action-adjusted history.** Yahoo chart source alone cannot establish completeness, split consistency across ticker transitions, or OTC trade/quote accuracy. Recent S&P/Quiver price anchors matched, but a serious **Oct 23 volume discrepancy** exists: Yahoo chart **8,225 shares** versus Stock Analysis/S&P **19,451 shares** (57.7% below S&P). The close was $0.75 on both. The difference requires investigation; do not treat Oct 23 volume as reconciled. Source references:
- https://stockanalysis.com/quote/otc/ZPTA/history/ (S&P Global Market Intelligence, Oct 23 update)
- https://www.quiverquant.com/stock/ZPTA/historical-prices/ (older historical reference)
- https://finance.yahoo.com/quote/ZPTA/history/ (Yahoo daily price convention)
- https://investors.zapataquantum.com/financials/sec-filings (corporate actions)

No paid real-time data is required merely to study completed daily closes; reliable broker quotes and tradeability will be required before real orders.

GitHub Actions: `ZPTA offline research tests` **39/39 passed** on commit `6ca3d3b`; the separate public-data candidate job also succeeded. Logs: https://github.com/brianreed31714/StockTracker/actions/runs/40048435872 . These are software/data-retrieval checks, NOT validation of model profitability or Windows activation.

## Research design

- Predeclared completed-day hypotheses: >=5% down close; two down closes totaling >=5%; down close >=10% below prior 10-day high; simple RSI(3) <=25; first higher close in top 35% of day range after >=5% down day.
- Signal known only after session t closes. Hypothetical entry **next-session OPEN**, exit at t+1, t+3, or t+5 session close. **Never** enter at the day's eventual low.
- Volume proxy: day-t close × volume >= $25,000. Cost sensitivity: **1% added to entry and 1% subtracted from exit** (~2% round trip), not an observed OTC spread.
- Chronological 70/30 split: 350 sessions through 2026-03-19 training, 151 sessions beginning 2026-03-20 holdout. Events whose exits cross split are purged.
- **For the table below, only the holdout is reported, and overlapping 3-day holding windows are removed using earliest-signal-first selection.** A simple iid event bootstrap (10,000 draws) provides rough mean uncertainty, not a valid clustered time-series inference. The holdout has now been examined and is no longer pristine for subsequent model tuning.

## Three-session holdout results — non-overlapping events, net of assumed costs

| Completed-day hypothesis | Independent trades | Mean net % | Median net % | Approx 95% iid bootstrap CI for mean % | Gross profit/loss | Full-allocation simulated max drawdown |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| One-day close decline >=5% | 19 | **-0.40** | +1.36 | -9.02 to +7.93 | 0.95 | -53.6% |
| Two declining closes totaling >=5% | 14 | **-0.96** | -4.59 | -7.89 to +6.57 | 0.84 | -41.4% |
| Down close >=10% below prior 10-day high | 32 | **-2.04** | -5.15 | -7.75 to +3.58 | 0.74 | -79.1% |
| RSI(3) <=25 | 24 | **-2.63** | -4.07 | -9.20 to +3.84 | 0.67 | -74.9% |
| Confirmed higher close after >=5% decline | 7 | **-0.51** | -4.16 | -8.24 to +9.03 | 0.89 | -28.4% |
| All eligible days (unmatched reference) | 47 | **-1.66** | -3.29 | -5.84 to +2.56 | 0.73 | -82.3% |

**None** of the five hypotheses achieved positive average 3-day net returns or profit factor >=1.25 on this independent-event holdout. Intervals include zero and event counts remain limited. Full-allocation drawdown assumes each non-overlapping event commits 100% of hypothetical capital; this is NOT the actual $150/$1,000 shadow-sleeve sizing. Position-size-aware portfolio risk remains untested, and printed next opens are not guaranteed fills.

### Matched controls (exploratory only)

For each non-overlapping signal, an eligible non-signal date in the same calendar month was matched on signal-day dollar turnover and range (not future returns). Controls may overlap, so these comparisons are **observational, not causal**.

- Two-down-day 3-day signals: +3.14 percentage-point mean net excess vs matched controls (14 pairs), bootstrap CI **-9.45 to +14.26**.
- RSI(3) <=25: +4.82-point excess (23 pairs), CI **-2.73 to +12.70**, despite **-2.63% absolute mean net return**.
- One-day >=5% decline: **-4.98-point** excess (19 pairs), CI **-18.41 to +7.13**.

No matched-control result establishes statistical or economic edge.

### Longer holding-period temptation

A one-day >=5% decline followed by a **5-session** exit produced **+4.34% mean** across **18 non-overlapping holdout events**, but **-0.81% median**, rough 95% iid CI **-8.45 to +18.34%**, a **-49.17% worst single net trade**, and **-56.2% full-allocation simulated maximum drawdown**. The apparent positive mean is insufficient for promotion; the downside is extreme.

## Current market and next-session signal

Friday **Oct 23**: S&P/Stock Analysis displayed close **$0.75** (+4.17%) on **19,451** shares, about **$14,588** of close-price turnover, below the predeclared $25,000 research floor. Yahoo reported only 8,225 shares. None of the five completed-day entry hypotheses fired at Oct 23 close; no next-session entry is supported by this model. This is a historical research observation, not a live order decision.

## Next work, ordered

1. Reconcile the Oct 23 volume mismatch and independently verify corporate-action-adjusted prices and volumes across the 501-session dataset. Cross-check OTCQB regime changes and the Oct 13 board authorization of a 1-for-2 through 1-for-50 reverse split; authorization is not execution.
2. Freeze these thresholds as exploratory. Future model-selection improvements require **fresh prospective forward data**, or a newly reserved independent holdout. The March–Oct 2026 period is already examined.
3. Research support zones, failed breakdowns and 1–5-day rebounds using **precommitted next-day limit-order scenarios**; the new `zpta_daily_validation.py` correctly marks both opening-price eligibility and intraday-low touches as **fill-unverified**, not actual fills.
4. Run broker spread/size/limit fill sensitivity, turnover regime segmentation, non-overlapping portfolio simulation with $150 maximum ZPTA position and $1,000 shadow cash, and realistic daily-loss controls. Require net expectancy, profit factor >=1.25, modeled drawdown <=8%, independent evidence and explicit approval before any execution redesign.
5. Continue GitHub PR/CI, keep all runtime routes PAPER_ONLY/SHADOW_ONLY. Latest Windows attestation is `HOST_PROCESSES_STABLE_SOURCE_ONLY`, not verified broker or EOD operation.

**Research takeaway:** Recent and longer-history evidence does NOT support blindly buying a ZPTA down day. The apparent 5-day bounce is dominated by highly variable outcomes, while short-term oversold/reversal rules have not beaten OTC cost and downside uncertainty. Focus next on liquidity-qualified, precommitted support-zone entries with no hindsight fills and genuinely new forward evidence.
