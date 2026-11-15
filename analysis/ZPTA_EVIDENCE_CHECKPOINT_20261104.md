# ZPTA close-only six-month evidence checkpoint — 2026-11-04

## Provenance and scope
User pasted Yahoo Finance historical OHLCV rows in chat (May 2026 through Nov 3 2026). A locally derived `zpta_6mo_close_streak_events.csv` contains **closing prices only**, May 4–Nov 3, with 126 evaluable next-day observations. This checkpoint was recomputed directly from that local CSV; the original Yahoo CSV and corporate-action-adjustment audit are **not** available in the repository. Do **not** treat this as a validated OHLCV/volume or executable-price backtest.

## Reproduced exploratory next-close outcomes
| Signal-day completed-close condition | n | Next close higher | Positive fraction | Mean next-close return |
| --- | ---: | ---: | ---: | ---: |
| All eligible | 126 | 54 | 42.86% | +0.182% |
| Exactly 2 consecutive declining closes | 16 | 9 | 56.25% | +1.247% |
| Exactly 3 consecutive declining closes | 6 | 3 | 50.00% | -0.387% |
| At least 2 declining closes | 25 | 14 | 56.00% | +1.107% |

These are *close-to-next-close* observations, not next-session open-to-exit trading results, not independent trades, not net returns and not portfolio ROI. They include no volume stratification. Prior exploratory bootstrap reported an interval spanning zero; this checkpoint does not claim a reliable edge.

## Priority blockers and implementation caveats
1. Obtain original precision OHLCV CSV, verify symbol continuity, splits/reverse splits, adjusted volume and date gaps. **Volume was provided in chat but is absent from the local event artifact**, so RVOL and the existing $25,000 signal-dollar-volume gate cannot be assessed honestly from this artifact.
2. PR #6 `analysis/zpta_daily_swing_research.py` already defines five fixed daily signals, 70/30 chronological split, next-open entry, 1/3/5-day exits, and 1% friction each side. Do not duplicate that engine with a separate unvalidated study; reconcile PR #42's RVOL research with PR #6.
3. Ensure any 3/5-session holdout results have embargoed overlapping exits, **non-overlapping selected trade outcomes**, weekday/volatility-matched baselines, liquidity sensitivity and uncertainty. Existing PR #6 admits its cohorts overlap.
4. Avoid labeling close-to-close up frequency as profitable strategy. OTC spreads and open fills are not verified. A limit touched by daily low does not prove a fill.
5. No news/noon cohort inference without timestamped data. Keep paper/shadow only. November 2 was conditional, not permission to go live.

## Reproduction
Local source: `/mnt/data/zpta_6mo_close_streak_events.csv` (not committed to GitHub). Python `csv.DictReader`; filter integer `down_streak`, calculate positive `next_return_pct` and arithmetic mean. Report is a **checkpoint**, not a complete validated dataset or CI result.
