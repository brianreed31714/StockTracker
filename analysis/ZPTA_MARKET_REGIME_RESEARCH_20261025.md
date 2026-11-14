# ZPTA Bottom Hunter — October 25, 2026: Market-regime leakage audit

**Decision: NOT READY for real-money automation.** This report adds a new, materially important finding to the October 23–24 daily-low research; it does not repeat or supersede the earlier risk evidence. Work remains read-only in draft PR #6. No broker orders, Windows deployment, thresholds or PAPER_ONLY / SHADOW_ONLY routing were changed.

## New finding: the 501-session backtest spans three fundamentally different quotation/tradability eras

The issuer explicitly announced that on **December 15, 2025** ZPTA had moved from the **OTC Expert Market to OTC Pink Limited** after becoming current in SEC reporting. On **June 16, 2026** the issuer announced that its **OTCQB quotation was effective for trading**. The intervening period may include other OTC quotation-tier changes and is labelled transitional; we do **not** assume Pink Limited for every intervening session. The pre-December period also includes the company's earlier Nasdaq listing and must **not** be mislabeled as uniformly Expert Market.

Primary issuer sources:
- https://investors.zapataquantum.com/news-releases/news-release-details/zapata-quantum-now-current-sec-reporting-enabling-broader
- https://investors.zapataquantum.com/node/8026/pdf
- Earlier Nasdaq delisting history is described in the June 2026 company S-1: https://investors.zapataquantum.com/static-files/91437e67-3e71-44a8-866a-c8a85b0a1914

**Why this matters:** historical daily prints during restricted or transitional trading cannot automatically be treated as equivalent to today's OTCQB broker-executable bid/ask liquidity. Pooling these sessions can make a backtest look better than an actual current-market strategy.

## Reproducible venue segmentation — source candidate, not certified

A fresh October 25 18:04 PT GitHub Actions fetch returned the same 501 daily candidate OHLCV sessions (2024-10-24 to 2026-10-23), with 5 zero-volume days, no reported Yahoo split events and independently unverified corporate-action adjustment. As of Oct 23 close:

| Issuer-anchored regime | Sessions | Median daily close × volume | Sessions meeting $25k turnover proxy |
|---|---:|---:|---:|
| Legacy pre-Dec 15, 2025 (mixed earlier Nasdaq/OTC Expert; unverified) | 285 | **$475.19** | **48/285 (16.8%)** |
| Post-Expert, pre-OTCQB transition (Dec 15–Jun 15) | 125 | **$73,645.08** | **109/125 (87.2%)** |
| OTCQB effective Jun 16, 2026 onward | **91** | **$77,320.38** | **77/91 (84.6%)** |

These are medians of daily **close × total reported volume**, not executable order-book liquidity. The source remains Yahoo's public delayed chart endpoint. The latest October 23 volume remains Yahoo **19,419** vs public S&P/Stock Analysis **19,451** shares (0.165% difference); earlier Yahoo publication was 8,225 and subsequently revised. Source-finalization and corporate-action verification remain incomplete.

## Current OTCQB-only five-session signal research

Signals use *completed* day t, buy no earlier than next-session OPEN, exit at day t+5 CLOSE; apply 1% hypothetical cost **each side**, $25,000 signal-day turnover proxy, earliest-signal-first non-overlap, and exclude any hypothetical position crossing a venue boundary. The same data have already been examined, so these results are **exploratory**, not an untouched out-of-sample validation.

| Signal | Independent OTCQB-era 5-day trades | Mean net position return | Median net position return | Rough 95% iid bootstrap mean interval |
|---|---:|---:|---:|---:|
| One completed-day close decline >=5% | **11** | **+3.03%** | **-9.60%** | **-10.43% to +21.08%** |
| Two down closes totaling >=5% | 10 | -4.55% | -8.39% | -13.88% to +7.13% |
| RSI(3) <=25 | 11 | -3.83% | -4.11% | -14.45% to +7.02% |
| Any liquidity-eligible session | 16 | -1.62% | -9.29% | -11.57% to +12.37% |

The 5% decline rule's positive mean is **not** proof of predictive edge: median is substantially negative, interval crosses zero, and there are only 11 independent hypothetical positions. Other preregistered 3-day tests were also evaluated by CI, but no strategy is promoted. All bootstrap intervals assume independent identically distributed events, likely understating regime/time-series uncertainty.

## NEW: current-OTCQB-only $1,000 / $150-capped shadow-sleeve simulation

Kept the original historical indicator lookback but permitted **only signal dates from June 16, 2026 onward**. $1,000 initial cash, at most $150 or 15% of current sleeve equity per position, one position at a time, 1% hypothetical cost each way, next OPEN / fifth CLOSE, no presumed low fills or stop execution.

| 5-session strategy | Positions | Hypothetical sleeve return | Close-mark maximum drawdown | Potential 3%-daily-budget breaches at LOW-price proxy |
|---|---:|---:|---:|---:|
| >=5% one-day close decline | **11** | **+4.99%** | **-15.87%** | **1** |
| Two down closes | 10 | -6.90% | -13.37% | 3 |
| RSI(3) <=25 | 11 | -6.55% | -12.50% | 3 |
| Any eligible day | 16 | -4.05% | -22.54% | 3 |

**Key comparison:** the earlier mixed-transition March–October holdout had shown +10.98% for the >=5% decline strategy at -15.10% drawdown; **restricting to the currently relevant OTCQB era reduces the hypothetical gain to +4.99% and increases drawdown to -15.87%**. Both fail the <=8% drawdown criterion. This is a sample-window comparison, **not** a causal estimate of how venue changes affected performance. Intraday-low proxy breaches are stress flags, not actual stop fills.

## Current signal and risks

Friday October 23 completed bar: close $0.75, Yahoo 19,419 shares, approximately $14,564 of daily close×volume, below the $25k research floor; none of five fixed daily entry rules triggered. No Sunday session; next regular U.S. market session is Monday October 26. **No model-qualified Monday buy signal.** No realtime quotes, broker ZPTA tradability, verified corporate-action-adjusted full history, executable spreads, depth, or actual order fills are available. Shareholder approval of potential reverse split in Oct 2026 is NOT proof of implementation; continue issuer/SEC checks.

## Engineering and verification

Added `analysis/zpta_market_regime_audit.py` and nine deterministic tests for venue boundaries, chronological as-of cutoffs, cross-venue exclusion, source liquidity, costs, and no-trade fail-closed behavior. Added optional `start_signal_date` to `analysis/zpta_daily_sleeve_risk.py`, preserving all prior defaults and historical indicator lookback, plus two new tests. Updated research CI to publish regime-separated metrics and OTCQB-only capped risk **without uploading proprietary historical bars or changing trading behavior**.

- **57/57 deterministic tests PASS** and candidate daily history/regime analysis job PASS: GitHub Actions https://github.com/brianreed31714/StockTracker/actions/runs/40252416697 (head 11c2cd31).
- Supervisor safety test run also PASS; unrelated infrastructure contract was still in progress when checked. Neither research CI nor GitHub merge verifies Windows broker execution.
- The 501 daily bars remain a Yahoo *source candidate*, not fully independent certified split-adjusted data.

## Next safe steps

1. Preserve frozen strategy parameters and examined March–Oct holdout; build forward dated signal snapshots from the **completed Oct 26 bar onward**, with independent future 1/3/5-session outcomes and no post-hoc parameter selection.
2. Reconcile market-tier history (especially before June 16), source revisions, corporate actions and pre/post-close data availability; prioritize OTCQB-era comparable sessions for current execution feasibility.
3. Quantify spread and liquidity impact only once broker-supported quotes are available; **no IBKR funding is needed solely for completed-day historical analysis**.
4. Require positive post-cost prospective edge, adequate independent samples, bounded drawdown <=8%, no hindsight low fills, and separate release approval before any real-money discussion. November 2 is a conditional review date, not automatic activation.
