# ZPTA historical dip-recovery study (research only)

Objective: test whether ZPTA declines recover quickly enough to support a distinct paper-only dip-recovery hypothesis. This is **not** authorization to alter live or shadow execution.

## Input
Obtain a reputable historical ZPTA daily OHLCV CSV with columns `date,open,high,low,close,volume`. Confirm OTC symbol identity, reverse splits, corporate-action adjustments, data gaps and trading-session chronology. Do not splice unadjusted and adjusted histories.

Run: `python analysis/zpta_dip_recovery.py zpta_daily.csv --output analysis/performance/zpta_dip_recovery.json`.

## Measures
- Close-to-close daily dips of 5%, 10%, 15%.
- Subsequent 1/2/3/5-session close-to-close returns, positive fraction, medians and means.
- Sessions to recover half or all of the closing-price loss, including censored observations.
- Separate future extension: intraday drawdowns, same-day recoveries, next-session open gaps, liquidity and bid/ask spread.

## Guardrails
- Dip signal observed at close cannot assume a fill at that same close. For actual strategy simulation, use next-session executable prices and include spread, slippage and liquidity.
- Split train/test chronologically; select thresholds only on training periods and evaluate untouched out-of-sample data.
- Avoid treating overlapping events as independent; compare with random-entry and buy-and-hold benchmarks.
- Report nonrecoveries and maximum adverse excursion; a quick rebound on some days does not guarantee dip-buying profitability.
- Do not enable live orders, modify risk limits, or promote the strategy without separately approved validation.

## Current status
Research script committed to a proposal branch. No market-data file ingested, backtest run, or verified empirical conclusion yet.
