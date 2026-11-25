# ZPTA November 2 live-readiness assessment — 2026-10-22

**Decision: NOT READY FOR REAL-MONEY AUTOMATION.** This is a research finding, not a blanket prohibition on future user-directed investing. Keep existing StockTracker PAPER_ONLY / ZPTA SHADOW_ONLY invariants unchanged; November 2 is a go/no-go review date, **not** a promised start date.

## Previously overlooked primary-source evidence

Examined committed `analysis/evidence/{2026-10-01,2026-10-02,2026-10-05,2026-10-06,2026-10-07,2026-10-08}/zpta_predictions.csv` and corresponding `zpta_observations.csv` in the connected repository. All percentages below refer to these six dated evidence folders; **no later runtime evidence is verified**.

| Test | Observed |
| --- | ---: |
| Prediction rows | 1,056 |
| Distinct bar timestamps across prediction files | 86 |
| Distinct bar/horizon combinations | 258 |
| Median elapsed time from `bar_ts` to `created_ts` | ~15.60 minutes |
| Signal reference price older than 60 seconds | **1,056 / 1,056 (100%)** |
| Predictions created at or after their target `due_ts` | **736 / 1,056 (69.7%)** |
| 5-minute forecasts created after their due time | **352 / 352 (100%)** |
| 15-minute forecasts created after their due time | **352 / 352 (100%)** |
| 60-minute forecasts created after their due time | **32 / 352 (9.1%)** |
| Observations exported in matching folders | 80 |
| Provider / observed volume | **80 Yahoo delayed / 80 zero-volume bars** |
| Last publicly committed `analysis/performance/latest.md` | **2026-10-08** |
| ZPTA simulated shadow trade rows in that report | **0** |

**Critical interpretation:** For the 5- and 15-minute cohorts, many “predictions” are created *after the stated outcome horizon*. Their reported correctness is not evidence of predictive skill. The 60-minute cohort is not reliable proof of tradable performance either, because its entry_price is the **15-minute-old bar close**, not a contemporaneous executable ask. Multiple models per bar share the same realized price path and must not be treated as independent trades. This is primarily timestamp/market-data contamination, **not evidence that a particular model's indicator is good or bad**.

**Zero-trade diagnosis:** The exported observations show Yahoo delayed provider on all 80 rows with 0 reported volume. In `zpta_specialist_v0_1.py`, `classify_regime()` sets `LIQUIDITY_DANGER` when five-minute dollar turnover < $25,000, among other conditions. `maybe_trade()` blocks entries in that regime. Thus the zero shadow trades are consistent with the expected **fail-closed liquidity gate**; lowering the entry threshold would not fix the missing market data, and overriding the liquidity gate would be unsafe.

The production trader imports `zpta_specialist_v0_1`; `zpta_specialist_v0_2_gate_audit.py` is not evidence of a running deployment. The StockTracker context explicitly enforces paper-only execution and ZPTA shadow isolation.

## Price-pattern research supports hypotheses, not profitability

The 2026-08-13 to 2026-10-22 public 50-session study in this draft PR found intraday drops >=5% in 21 sessions, of which 14 recovered at least half their low-to-prior-close decline **by the close**, but a hypothetical next-day open-to-close scenario had **-0.93% average after 1% assumed cost each side** for the eligible subset. Rounded public OHLCV, the small sample, and unknown intraday sequencing prevent a tradable-backtest conclusion. No validated positive expectancy yet.

As a contemporary liquidity illustration, public delayed data show **~39,626 shares on Oct 22** versus **798,918 on Oct 16**; an apparent price surge may be accompanied by large volume swings. These figures are not actual order-book depth. Source: https://stockanalysis.com/quote/otc/ZPTA/history/ (Oct 22 ~3:58pm ET display).

## Candidate predictive indicators — preregister before optimizing

A. **Failed breakdown / confirmation:** after a sharp decline identified from past prices only, require a higher low, reclaim of a prior 5-minute reference, and accelerating executed volume, then measure subsequent forward 5/15/60-minute returns. Do not assume fills at the daily low.

B. **Volume-confirmed breakout:** demand expansion of rolling 5-minute dollar volume relative to known prior-session baselines, momentum persistence, and contemporaneous bid/ask liquidity. Reject if expected upside is less than estimated round-trip execution cost plus safety margin.

C. **VWAP reclamation:** cross above session VWAP after a selloff plus strengthening relative volume and no stale quote; compare with continuation / random time-matched benchmarks.

D. **Anti-chase/avoidance:** unfavorable spread, no real volume, stale trades, large opening gap, exhaustion wick, pending corporate action or trading halt should veto candidate entries.

Do **not** pick parameter thresholds based on the untouched out-of-sample period; select only on training windows, then walk forward with embargo around overlapping forecast horizons. Report independently clustered trade counts, median and mean net returns, payoff ratio, profit factor, worst adverse excursion, maximal drawdown, and bootstrap confidence intervals by trading day. Require precision **minute trades plus bid/ask** to simulate next executable quote and conservative fills; daily OHLC cannot order the low/high intraday. Historical returns are not guaranteed.

## Ordered gates for a live decision

1. **Market-data entitlement:** Obtain verified real-time ZPTA trade-and-quote data, with independent timestamps, positive volume and a measurable bid/ask spread. Alpaca's official market-data FAQ says OTC data requires a special broker-partner subscription. Check a supported alternative provider/broker; never call `yahoo_delayed` “live.” Ref: https://docs.alpaca.markets/us/docs/market-data-faq .
2. **Broker eligibility:** Confirm the selected broker accepts opening orders in **ZPTA's current OTC tier**, and the security reports tradable. Alpaca's documented OTC order capabilities are tier-dependent; asset lookup alone may report `tradable=false`. Ref: https://docs.alpaca.markets/us/docs/orders-at-alpaca .
3. **Causality:** Forecast creation and executable quote must precede the measured outcome; eliminate stale bar-price fills and future leakage. Require 0 after-due forecasts for promoted horizons.
4. **Robustness:** Split-consistent historical data, untouched chronological holdout, sufficient independent outcomes, positive **net** expectancy under conservative realistic costs, profit factor >=1.25, and modeled maximum drawdown <=8% (from existing StockTracker criteria). Require 20 reliable shadow sessions and at least 300 legitimately timed resolved forecasts as a minimum already documented in STOCKTRACKER_CONTEXT.md; this is necessary but **not sufficient** to establish profitability.
5. **Operations:** Demonstrate recent sanitized daily reporting, reproducible results, data-staleness fail-closed behavior, kill switch, hard position/daily-loss limits, broker rejection handling, limit-order support and 5 consecutive stable paper sessions. Verify Windows supervisor/deployer independently.
6. **Separate approval:** No live-trading code, secrets, routes, or order submission is authorized by this study. A distinct explicit release approval and broker-specific risk review are necessary.

Nov 2, 2026 is a **Monday**. There are only six US regular trading sessions remaining after Oct 22 and before Nov 2 (Oct 23 and Oct 26-30), insufficient to accumulate the missing 20 clean forward sessions from scratch.

## Action

Run the read-only latency audit as part of research QA:

```sh
python analysis/zpta_signal_latency_audit.py analysis/evidence/*/zpta_predictions.csv --fail-on-hindsight
```

It is expected to **fail** on these historical files, which is an accurate result, not a CI regression. The default invocation emits JSON without a failing exit status; the strict flag is for the future qualification gate.

Request verified current quotes and current runtime evidence through the authorized publication workflow; diagnose OTC entitlement/feed quality *before* strategy calibration. Do not change live execution or weaken `LIQUIDITY_DANGER`.
