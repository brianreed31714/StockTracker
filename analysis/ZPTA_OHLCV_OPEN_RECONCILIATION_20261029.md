# ZPTA Bottom Hunter — 2026-10-29 OHLCV opening-print evidence audit

**Decision: NO VERIFIED BUY / NO-GO FOR LIVE TRADING.** New read-only investigation building on PR #6, not retuning frozen daily hypotheses. Objective remains next-session to 1/3/5-session dip entries before multi-day recovery.

## Material finding: close/volume agreement does NOT validate next-session opening fills

Independent public histories display substantially different **opening prices** even when close and volume agree or nearly agree. This matters because the preregistered simulation enters at next-session OPEN, not the prior session's low.

| Session | S&P/Stock Analysis displayed open | EODData displayed open | Relative difference vs EODData | Close in both | Implication |
| --- | ---: | ---: | ---: | ---: | --- |
| 2026-10-23 | $0.8000 | $0.7360 | **8.70%** | $0.7500 | Opening-price strategy outcomes cannot be independently verified |
| 2026-10-26 | $0.7500 | $0.6900 | **8.70%** | $0.7200 | Close/volume-only anchor check misses material opening discrepancy |
| 2026-10-22 | $0.7500 | $0.7800 | **3.85%** | $0.7200 | Differences occur on additional dates |

Sources observed October 29:
- S&P Global Market Intelligence display: https://stockanalysis.com/quote/otc/ZPTA/history/
- EODData: https://eoddata.com/stockquote/OTCBB/ZPTA.htm

These are differences in **published opening prints**, not evidence either provider is dishonest. Venue coverage, opening definitions, delayed publication and rounding may contribute. Do not choose the favorable open after seeing returns.

### New Oct 29 source-freshness / precision warning

At the October 29 18:00 Pacific research check, S&P/Stock Analysis showed a quote header **$0.7350 at 3:50 PM Eastern**, while its Oct 29 historical row displayed a **rounded $0.74 close and 45,468 shares**. Its page stated updated October 29, but the header timestamp is **before the official 4:00 PM Eastern close**. EODData still listed **October 28** as latest completed day. The $0.7350 vs $0.74 display difference is ~0.68%, large relative to our small-edge hypotheses.

**Do not freeze or score Oct 29 as a finalized, independently reconciled session based on these observations.** Oct 26 3-session and Oct 28 1-session prospective outcomes mature today but remain quality-blocked (Oct 26 original volume mismatch; Oct 28 prior-close revision changed RSI signal). No new independently verified prospective trade outcome or real-world fill is established.

### Same-day versus multi-day outcomes

Oct 26's reported low $0.631 to close $0.72 was a **same-day low-to-close recovery**; it is not evidence of a profitable next-session fill or multi-day rebound. Oct 27 close $0.73 and Oct 28 close $0.73 are observed subsequent daily closes. No validated 1/3/5-session trade return is promoted.

## Read-only engineering in PR #6

Added analysis/zpta_daily_ohlcv_reconcile.py: timestamped, two-source full-field OHLCV comparison, per-field discrepancy %, date/zero-volume checks and explicit fail-closed promotion status. It does **not** certify corporate actions or broker execution.

Added tests/test_zpta_daily_ohlcv_reconcile.py: 10 deterministic tests including Oct 23 and Oct 26 opening discrepancies, mismatched volume, missing/duplicate dates, zero-volume, invalid bars and timestamp/source safeguards.

The existing ZPTA research workflow discovers test_zpta_*.py and triggers on these paths. Ten new tests passed locally before commit; **full GitHub CI status must be independently checked after these commits**. This is a quality-control increment, not a complete independent two-year provider feed or profitable strategy.

## Remaining hard evidence gates

1. **Complete adjustment ledger:** SEC/FINRA effective actions, historical symbol/venue changes, split factors, adjusted **prices and volumes**, independent two-provider 501-session precision-level comparison and hashes/as-of timestamps. SEC October 9 meeting approved potential reverse-split authority, but authorization alone is not an effective action: https://www.sec.gov/Archives/edgar/data/1843714/000149315226046819/form8-k.htm.
2. **Executable OTC liquidity:** timestamped broker/venue bid, ask, size, routing permission and spread/market impact; EODData displays **bid 0 / ask 0**, not a usable executable quote. A ~15-minute delay is acceptable for historical EOD study but not proof of execution. Do not fund IBKR merely for historical research.
3. **Predictive robustness:** preserve frozen decline, two-down-day, 10-day drawdown, RSI3 and reversal-confirmation hypotheses. After source reconciliation, test next-open/precommitted limits without low-touch fills, 1/3/5-session exits, matched eligible-day controls, independent non-overlapping events, chronological holdout with embargo, OTC cost sensitivity, confidence and <=8% portfolio drawdown. Already-examined holdout is not fresh proof.
4. **Forward results:** continue immutable prospective snapshots and score only after source-quality gates pass. No parameter revisions after viewing outcomes.

**Safety:** PAPER_ONLY / ZPTA SHADOW_ONLY. No execution settings, risk limits, Windows services or broker orders changed. November 2 remains conditional NO-GO unless all evidence gates and acceptable net/drawdown results are independently demonstrated.
