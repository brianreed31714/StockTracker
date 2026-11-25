# ZPTA daily-low research checkpoint — Saturday, October 24, 2026

**Decision: NOT READY FOR REAL-MONEY AUTOMATION.** All work remains read-only in draft PR #6; paper-only/ZPTA shadow-only invariants unchanged. November 2 remains a conditional evidence review, not a deployment date.

## New since October 23

1. **Position-capped, cash-aware daily-swing risk analysis is implemented and CI-tested.** Added `analysis/zpta_daily_sleeve_risk.py`, seven deterministic tests, and a candidate-history GitHub Actions reporting step. The analysis assumes a $1,000 starting shadow sleeve, max $150 or 15% of sleeve equity invested per trade, 1% hypothetical cost each way, one non-overlapping position at a time, signal after completed day t, buy at next-session OPEN, sell at the close after 1/3/5 sessions. It marks held positions daily to a hypothetical net close, and separately checks pessimistic daily LOW marks. These are **not executable fills, real-time orders, or reliable stop execution**.
2. **All 46 offline research tests passed** in GitHub Actions run [40148776612](https://github.com/brianreed31714/StockTracker/actions/runs/40148776612) (commit `52ce8b72`). Candidate 2-year data retrieval and research job also passed. These verify deterministic software behavior, **not predictive edge**.
3. **October 23 Yahoo volume revised substantially after the earlier report.** The Oct 23 job had read 8,225 shares versus S&P/Stock Analysis 19,451. The October 24/25 UTC repeat fetched **19,419 Yahoo shares** versus **19,451 S&P**, a remaining discrepancy of **32 shares (0.165%)**, with matching $0.75 close. Yahoo's number changed between fetches; the reason is unverified, so retain a data-finalization delay/reconciliation gate. Other public anchors Oct 22, Oct 16, Oct 8 matched both closing price and volume; Aug 25 matched volume and closing price to ~0.002%. Public source: https://stockanalysis.com/quote/otc/ZPTA/history/ (S&P Global Market Intelligence, last updated Oct 23). The Yahoo dataset is still **NOT independently verified split-consistent corporate-action-adjusted history**.
4. **Current completed-day liquidity remains too low for an entry signal.** Oct 23: $0.75 close × 19,451 shares = $14,588 approximate dollar turnover, below the predeclared $25,000 threshold. None of the five completed-day entry signals fired. The next US regular session is Monday Oct 26. This is not a live quote or an executable recommendation.

## NEW: 5-session risk at actual configured ZPTA shadow sleeve sizing

Replayed candidate Yahoo 501-session history, 151-session examined holdout (Mar 20–Oct 23), using predeclared signal families, 1% hypothetical cost each side, earliest-signal-first non-overlap. **The holdout has already been examined and is NOT a pristine test set.**

| Five-session signal | Independent positions | Ending $1,000 sleeve equity | Sleeve return | Maximum close-mark drawdown | Worst intraday-low proxy drawdown | Days whose low-price proxy breaches 3% daily sleeve loss budget |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| >=5% down close | 18 | $1,109.81 | **+10.98%** | **-15.10%** | -16.49% | 5 |
| Two down closes totaling >=5% | 13 | $915.46 | -8.45% | -13.83% | -16.34% | 4 |
| RSI(3) <=25 | 17 | $884.98 | -11.50% | -17.13% | -20.05% | 7 |
| All eligible sessions (reference) | 27 | $1,016.90 | +1.69% | -21.72% | -24.74% | 9 |

**Interpretation:** The +10.98% five-session *sleeve-level* scenario for buying after >=5% down days is not validated alpha. The prior position-return distribution was dominated by outliers (median -0.81%, worst single position return -49.17%, bootstrap mean CI -8.45% to +18.34%). At $150 maximum exposure, the **-49.17%** hypothetical position loss corresponds to **-$73.76**, or **-7.38% of a $1,000 sleeve**. That is **2.46×** the configured 3% ($30) daily-loss budget, if it occurred within one session; OTC gaps and missing liquidity can bypass stops. Even the scaled scenario has **-15.10%** close-mark drawdown, exceeding the **8%** model promotion target. The 5 low-mark daily-budget breaches are *potential* violations, not observed executed stop losses.

**Additional caveats:** Hypothetical next-open prices are not guaranteed fills; actual OTC spread/slippage may be >1% each side. No order-book depth, queue, halt, price/volume data provenance certification, borrow or broker tradeability verified. Marks to intraday lows do not determine time order or guarantee an exit. Full sleeve idle cash earns no interest in this scenario. Signal thresholds were already examined on this holdout; no parameter optimization is authorized from these results.

## Corporate-action gate and event risk

The company's October 13 Form 8-K documents October 9 shareholder approval of discretionary reverse split authority between 1-for-2 and 1-for-50, **not an executed split**. Yahoo's retrieved payload reported no split events, but that is insufficient independent certification across all 501 sessions. Continue SEC/issuer effective-date checks before relying on adjusted OHLCV or promoting any model. Primary issuer filings: https://investors.zapataquantum.com/financials/sec-filings . Issuer release list as of Oct 24 shows latest Oct 20 advisory board announcement, no later press release. https://investors.zapataquantum.com/news-releases .

## Next actions (no threshold mining)

- **Freeze** these exploratory rule parameters and the examined March–Oct 2026 holdout; validate on fresh prospective sessions, not by selecting the +10.98% result after inspection.
- Add reproducible daily source-finalization checks (re-fetch post-close and following day, cross-provider volumes/adjustments, record raw payload hashes without distributing proprietary data).
- Use only completed-day signals and precommitted next-session entry zones; continue fill-unverified limit scenarios and risk controls. Test realized spread, depth, gap risk and broker eligibility only when real-money consideration is justified; no need to purchase IBKR feed for EOD research alone.
- Evaluate precommitted support-zone and reversal-confirmation features *prospectively*, with independent non-overlapping trade observations, matched controls, clustered uncertainty, 1/3/5-session holding outcomes, bounded sleeve drawdown and conservative execution.
- Check GitHub CI and Windows attestation separately; no new Windows deployment or real-money order path has been activated.

**Evidence:** GitHub Actions [ZPTA offline research tests run 40148776612](https://github.com/brianreed31714/StockTracker/actions/runs/40148776612), draft PR #6, `analysis/zpta_daily_robustness.py`, `analysis/zpta_daily_sleeve_risk.py`, and published 501-session October 23 report.
