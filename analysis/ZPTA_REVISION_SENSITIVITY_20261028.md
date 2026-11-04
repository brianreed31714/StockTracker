# ZPTA Bottom Hunter — October 28, 2026 EOD source-revision sensitivity

**Decision: NO VERIFIED BUY; NOT READY FOR REAL MONEY.** This report advances the already approved day-to-day 1/3/5-session bottom-hunting research in draft PR #6. The Oct 28 research candidate is technically flagged, but its classification **changes when one previously published prior-day close is revised**. A reproducible fail-closed audit now prevents promotion or forward-outcome scoring until source quality is reconciled. No execution or Windows changes.

## New completed-day observation and reproducible revision effect

The Oct 28 18:00 PT research workflow fetched **501 Yahoo candidate daily bars** (2024-10-29 through 2026-10-28), five zero-volume sessions, no reported Yahoo split events. The full history's corporate-action adjustment is **not independently verified**. The frozen Oct 28 source candidate is:

| Metric | Oct 28 Yahoo candidate | Independently displayed S&P/Stock Analysis |
| --- | ---: | ---: |
| Close | $0.73 | $0.73 |
| Low | $0.73 | $0.73 (display precision) |
| Volume | 89,806 | 89,806 |
| Close × volume proxy | $65,558.38 | $65,558.38 |
| RSI(3), with refreshed prior bars | **25.0000** | Not independently computed |

Stock Analysis's Oct 28 historical row matched the candidate close/volume when checked; its quote header was timestamped **3:56 PM Eastern** and its historical table said updated Oct 28, so final publication/revision timing is not fully established. One matching date is not a verified two-year data series or executable bid/ask. Source: https://stockanalysis.com/quote/otc/ZPTA/history/ (S&P Global Market Intelligence).

**Material new finding:** The original October 27 Yahoo research candidate was frozen at **close $0.74 / volume 14,491** (prior GitHub Actions run 40612642610, documented in `analysis/ZPTA_DAILY_LIMIT_AUDIT_20261027.md`). The newly retrieved Yahoo Oct 27 bar is **$0.73 / 35,982 shares**, matching the independently displayed S&P Oct 27 close/volume. That revision changes the Oct 28 three-day RSI calculation:

| Previous-day source used for Oct 28 calculation | RSI(3) | Frozen rule `rsi3_at_most_25` |
| --- | ---: | --- |
| Refreshed Oct 27 close **$0.73** | **25.0000** | **Triggers** |
| Originally frozen Oct 27 close **$0.74** | **33.3333** | **Does not trigger** |

This is not evidence of manipulated data or proof the refreshed price is wrong. It is evidence that the **candidate is sensitive to a source revision**. The model must preserve the original frozen input and document revisions, not silently claim a robust predictive edge. The Oct 28 low equaled the close in the Yahoo source; no same-day low-to-close rebound occurred. A future multi-day rebound has **not yet been observed**.

The research snapshot is frozen with:
- `completed_day_signal_flags=["rsi3_at_most_25"]`
- `prior_source_revision_status=REVISION_CHANGED_SIGNAL_DO_NOT_PROMOTE`
- `research_promotion_blocked=true`
- `future_outcomes={1d:null,3d:null,5d:null}`
- `real_money_trading_allowed=false`
- `input_ohlcv_sha256=6aed517dfb20522a936ed5a291a4a9fb2acbcb55f9085d7fbbb3b9643bdadf63`

**Source-of-truth warning:** the Oct 26 frozen candidate itself remains `SOURCE_MISMATCH_DO_NOT_PROMOTE` because its first Yahoo volume disagreed with S&P by 75.69%. The observed Oct 27 S&P close $0.73 vs Oct 26 close $0.72 is a **+1.39% close-to-close move**, not a verified filled trade or demonstrated profitable rebound. A hypothetical Oct 27 open $0.72 to close $0.73 after 1% friction each side is **-0.62%**; the frozen source mismatch means this must not be promoted as a validated prospective score.

## Engineering delivered in PR #6 (read-only)

1. `analysis/zpta_signal_revision_sensitivity.py`: compares the current completed-day signal with a counterfactual using the previously frozen preceding-day close/volume, without modifying input bars. It outputs both RSI(3) values and a `REVISION_CHANGED_SIGNAL_DO_NOT_PROMOTE` gate, with no trading capability.
2. `analysis/zpta_prospective_daily_snapshot.py`: accepts a dated prior-revision audit and embeds the quality gate in the **first immutable snapshot write**, without altering the frozen five signal rules or inventing future returns.
3. `analysis/zpta_prospective_outcome_score.py`: refuses to score mismatched signal-day sources or snapshots whose prior-bar revision gate blocks promotion.
4. `.github/workflows/zpta-research-tests.yml`: audits the known Oct 27-to-28 source revision on the Oct 28 completed bar, persists derived audit metadata in the prospective snapshot artifact, and keeps original raw daily OHLCV off GitHub.

**CI:** The latest research run [40797864649](https://github.com/brianreed31714/StockTracker/actions/runs/40797864649) passed **103 deterministic tests** and the candidate-history research job, including the actual Oct 28 source-revision sensitivity replay. Supervisor restart safety checks passed on the same code head; infrastructure contract status must be verified separately before merge. CI validates code mechanics, **not** source truth, broker fills, Windows runtime or a profitable strategy.

## Forward scoring and November 2 gates

- Oct 28's frozen signal can be observed at 1 session on **Oct 29**, 3 sessions on **Nov 2**, and 5 sessions on **Nov 4**, *only if source-quality gates are reconciled*. Do not score today using future data or alter the preregistered RSI threshold after seeing returns.
- Oct 26's frozen ten-day-high drawdown candidate's 3-session and 5-session horizons mature **Oct 29** and **Nov 2**, respectively, but its original provider mismatch still blocks validated scoring.
- Continue checking finalized S&P/Yahoo bars, corporate-action filings, independent venue liquidity, printed-price vs executable bid/ask/size, conservative 1%+ cost scenarios, chronological embargo, non-overlapping positions and drawdown. No IBKR funding required for completed daily historical research.
- Current OTCQB-only prior five-day >=5%-down-close shadow-sleeve research showed **-15.87% drawdown**, beyond the <=8% target; positive net edge has not been validated on a fresh independent sample.

**Operational invariant:** PAPER_ONLY / ZPTA SHADOW_ONLY. No merged PR, trading code deployment, risk-setting change, broker order, or verified Windows activation. November 2 is a conditional readiness review, **not** an automatic live launch.
