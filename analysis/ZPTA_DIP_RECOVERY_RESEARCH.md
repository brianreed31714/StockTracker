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


## 2026-10-22 checkpoint: intraday descriptive extension (NOT strategy validation)

Committed `analysis/zpta_intraday_recovery.py` and six deterministic tests in `tests/test_zpta_intraday_recovery.py` to this research branch. All six passed in a local Python unittest run before publication; GitHub CI and Windows runtime are **not** verified. The module is offline/read-only and never changes the running ZPTA specialist.

**Source and scope:** 50 publicly displayed daily OHLCV sessions, 2026-08-13 through 2026-10-22, from StockAnalysis/S&P Global Market Intelligence, https://stockanalysis.com/quote/otc/ZPTA/history/ (checked October 22). The free display rounds OHLC to $0.01, so derived percentages and threshold counts are **approximate and rounding-sensitive**. The October 22 quote was displayed at 3:58 p.m. Eastern, potentially before the official close. Raw third-party data are not redistributed in this repository. The issuer's LSEG historical-price page explicitly displayed a 1:1 cumulative split factor for October 12–16, https://investors.zapataquantum.com/stock-info/historical-price-lookup ; this does **not** validate every earlier session or rule out later corporate actions. ChartExchange showed no recorded split as of October 21, https://chartexchange.com/symbol/otc-zpta/historical/splits/ . Verify official corporate-action history and a precision-priced licensed dataset before any real backtest.

**Definition:** event = day's *low* at least 5%, 10%, or 15% below previous close. Recovery = same day's *close* recovering at least half or all of the prior-close-to-low decline. It is descriptive only: intraday low/high ordering and executable bid/ask prices are unknown. The hypothetical next-session open-to-close scenario uses signal-day liquidity, a $150 position cap, 1% of signal-day dollar volume, $25 minimum notional, $25,000 minimum signal-day dollar volume, and symmetric assumed costs (not observed spreads).

| Intraday dip | Events | Half recovered by same close | Fully recovered | Next-session gross mean (all observable) | Next-session net mean (liquidity eligible, 1% cost each side) | Net sample |
|---|---:|---:|---:|---:|---:|---:|
| >=5% | 21 | 14 | 5 | +1.02% | -0.93% | 20 |
| >=10% | 9 | 6 | 2 | +1.46% | -0.55% | 9 |
| >=15% | 4 | 2 | 0 | -2.40% | -4.33% | 4 |

For context, an unconditional next-session open-to-close sample passing the same liquidity proxy had 39 observations and -2.78% mean after the same 1%-each-side hypothetical costs. This is **not** a causal or risk-adjusted benchmark: sessions are overlapping, the market regime is narrow, and entry at the next open may be infeasible. A simple 5-session non-overlap selection reduced the >=5% eligible dip sample to 7, with -2.55% mean net return. Results are sensitive to selection and assumptions; do not optimize on these 50 sessions.

**Validation gate:** 50 sessions produce only 35 training and 15 test sessions under a 70/30 split; the code requires at least 100 training and 30 untouched test sessions. Status = INSUFFICIENT_HISTORY. No actual intraday tick/order-book sequence or bid/ask observations were available. No candidate is eligible for promotion, and no deployment request has been created.

**Next steps:** (1) obtain a complete split-consistent precision daily history with provenance; (2) acquire minute and bid/ask or trade-and-quote data to test whether a signal can occur *before* the rebound; (3) train only on chronological training data, test untouched out-of-sample data and independent event clusters; (4) evaluate actual OTC fills, costs, drawdown, liquidity and baseline alternatives; (5) keep the specialist shadow-only and seek approval through the existing release gates if evidence becomes sufficient.
