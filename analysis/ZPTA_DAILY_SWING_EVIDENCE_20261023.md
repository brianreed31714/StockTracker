# ZPTA daily low research — provisional 51-session evidence (2026-10-23)

**Status: EXPLORATORY, NOT A VERIFIED TRADABLE BACKTEST.** No change to paper-only / ZPTA shadow-only execution. This is a deliberately bounded check to identify whether the proposed completed-day rules deserve a larger, independently sourced and split-consistent historical test.

## Provenance and known limitations

- Observations: 51 consecutive reported trading sessions from **2026-08-13 through 2026-10-23**, including Oct 23 closing data.
- Historical OHLCV Aug 13–Oct 8 was manually checked against the public **Quiver** ZPTA daily-price table, snapshot dated Oct 8. Later Oct 9–23 data came from **Stock Analysis** (S&P Global Market Intelligence), last updated Oct 23, with occasional rounded fields; Oct 16 opening price was cross-checked with the Twelve Data display. **This is a mixed-provider preliminary transcription, not a complete, machine-reproducible licensed data extract.** Do not use it to calibrate or promote a strategy.
- Public sources: https://www.quiverquant.com/stock/ZPTA/historical-prices/ ; https://stockanalysis.com/quote/otc/ZPTA/history/ ; https://twelvedata.com/markets/939465/stock/otc/zpta/historical-data .
- Quiver states its OHLC values are as traded and its adjusted close is split/dividend adjusted; Stock Analysis states its prices are split-adjusted. Cross-provider precision and corporate-action equivalence were **not independently verified**. Example: Oct 16 opens differ between Quiver ($0.5250) and Stock Analysis (~$0.54). **No full-length verified dataset obtained.**
- A completed day-t signal hypothetically enters at **day t+1's reported OPEN**, exits at the CLOSE of day t+1, t+3 or t+5. No intraday low fills or hindsight-selected entry points.
- Filter: only signal-day close × volume >= $25,000. Of 40 potential signal days after 10-session warmup and excluding last day, 33 passed. This turnover proxy is NOT proof of actual order-book depth.
- Cost scenario: 1% added to entry and 1% deducted from exit (approximately 2% round trip). **Actual OTC spreads and fills may be substantially worse.**
- Signals: predefined rules in `analysis/zpta_daily_swing_research.py`. The summary below is an offline reproduction of that rule logic on manually transcribed public data, not proof the CLI was run on a verified CSV. Multiple signals overlap. Sample too short for the minimum 100 training + 30 holdout sessions. No legitimate out-of-sample validation.

## Descriptive findings, 1% each-side cost

| Completed-day signal | Exit after | Overlapping event observations | Mean net % | Net wins |
| --- | ---: | ---: | ---: | ---: |
| All liquidity-proxy eligible sessions | 1 session | 33 | -3.91 | 18% |
| One-day close decline >=5% | 1 session | 5 | **-8.65** | 20% |
| Two declining closes totaling >=5% | 3 sessions | 7 | +2.08 | 43% |
| Down day, close >=10% below prior 10-session high | 3 sessions | 16 | +0.19 | 44% |
| RSI(3) <=25 | 3 sessions | 12 | -3.42 | 50% |
| All eligible sessions | 3 sessions | 31 | -2.86 | 32% |

**The superficially positive 3-session averages are not robust.** Purging overlapping holding periods by selecting the first eligible event after each prior exit:

| Signal / 3-session exit | Non-overlapping events | Mean net % | Median net % | Mean lowest-low excursion from entry open |
| --- | ---: | ---: | ---: | ---: |
| Two declining closes totaling >=5% | **4** | +0.92 | -4.69 | -11.49% |
| Down day >=10% below 10-session high | **9** | -0.21 | -3.66 | -11.98% |
| All eligible sessions | **13** | -3.93 | -4.34 | -12.75% |

The four non-overlapping two-down-day outcomes were approximately **-4.34%, -5.04%, -17.82%, +30.88%**. Remove the single large winner and the mean becomes **-9.07%**. A basic iid event bootstrap (10,000 resamples, fixed seed 20261023; not valid for strong time dependence) yields a **95% mean interval of about -14.45% to +21.90%**. This is far too uncertain to assert predictive skill. Worst-low excursions are descriptive, not stop-loss fills.

## Latest completed session, Friday Oct 23

Stock Analysis shows close **$0.75**, up **4.17%** from $0.72, on **19,451 shares**. Reported close × volume is only **~$14,588**, below the predeclared $25,000 minimum. None of the five completed-day entry hypotheses fired on Oct 23. **No hypothetical entry is supported by this research on the latest completed day.** This is not a recommendation to buy, sell, or short.

Source: https://stockanalysis.com/quote/otc/ZPTA/history/ (Oct 23 last update; delayed quotes). The $0.75 close does not establish current executable bid/ask.

## New insight and next gates

1. **Blind dip buying performed especially poorly in this small recent sample.** The one-day >=5% down cohort averaged -8.65% net for next-session open-to-close with only five cases. This argues for testing reversal confirmation and avoiding falling knives, not changing live thresholds.
2. A **three-session** rebound hypothesis deserves research because a handful of extreme winners dominate averages; require many independent observations, trimmed/median returns, adverse excursion and drawdown. A positive mean alone is insufficient.
3. The Oct 23 dollar turnover was below the research floor. No claimed current tradeability or fill probability.
4. Acquire at least ~130+ verified split-consistent sessions (prefer a full year+ and independent source comparison), preserve original precision and provenance, audit reverse-split announcements versus effective events, and rerun the module on an untouched chronological holdout.
5. Extend research to conservative limit-order **fill/no-fill** scenarios, compare to matched-date controls, add day-clustered confidence bounds and non-overlapping portfolio simulation. No same-day low fills or post hoc threshold selection.
6. Run GitHub research unit tests and CI independently. Do not equate green infrastructure workflows with tested ZPTA model performance.

**Readiness decision:** Still **NOT READY** for real-money ZPTA automation. November 2 is a conditional evidence review only.
