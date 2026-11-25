# ZPTA missed-rebound investigation — approved scope (2026-10-27)

User approved improvements 1–5. This document starts the controlled research track; it does **not** assert that implementation, tests, CI, or Windows activation have passed.

## Baseline verified in repository
- `zpta_specialist_v0_1.py` is shadow-only; no broker order route.
- `maybe_trade` rejects entries in `LIQUIDITY_DANGER`, below `ENTRY_SCORE=68`, after entry cutoff, beyond daily trade/loss limits, or above spread threshold.
- `classify_regime` flags five-minute dollar volume < $25,000, spread proxy > 8%, or fewer than two trade bars in five minutes; bullish scores are capped at 45 in that regime.
- Provider preference: Alpaca OTC, Yahoo delayed fallback.
- Published 2026-10-27 sanitized summary: zero ZPTA resolved predictions and zero ZPTA shadow trades; quality LIMITED. No evidence that any specific visible chart rebound was executable.
- Current review reports lack validated per-opportunity block reasons, quote-level bid/ask and timestamped realized fills.

## Approved research work, in order
1. **Blocked-opportunity ledger**: append sanitized, bounded rows for every evaluated candidate with bar timestamp, receipt timestamp, provider, data age, model/ensemble scores, market regime, spread proxy, 5-minute dollar volume, 5-minute trade-bar count, explicit *all* block reasons, and subsequent 5/15/60-minute and next-session outcomes. Record missed-opportunity forward outcomes even if entry blocked. No order submission.
2. **Oct 21–27 chronological replay**: replay immutable, timestamped, provenance-tagged source bars; never use future bars in signal construction; explicitly classify unobservable periods and bar revisions. Report detected vs missed rebounds and realizable return after conservative spread, fees and slippage, not chart extrema.
3. **Dip Recovery Hunter shadow model**: independently score drawdown magnitude, stabilization, liquidity, reversal confirmation, and rebound durability. Compare with existing four models in walk-forward holdout; report return on allocated capital, trade count, max drawdown, exposure, and uncertainty. No live route.
4. **Data-feed investigation**: compare Alpaca OTC entitlements and bar freshness vs delayed Yahoo; quantify lag, sparse-minute coverage, revised volume and price, and absence of executable quotes. No credential logging.
5. **Liquidity-gate counterfactual**: preserve existing entry restrictions in active code; simulate multiple thresholds offline with fill feasibility, loss and drawdown limits, and abstention rates. Never remove the hard liquidity block without explicit gated approval and convincing evidence.

## Engineering gates
- Add deterministic tests for time alignment, no-lookahead, missing bars, stale feed, block-reason completeness, replay determinism, daily-loss and paper-only invariants.
- CI required checks pass before merge; PR review before merge; deployment agent must verify loaded code independently.
- Keep PAPER_ONLY and all current risk settings unchanged; no service restart, deployment request, or Pushover from this research PR.
- Published report must distinguish **verified actual shadow trades** from **counterfactual replay** and **missing evidence**.
