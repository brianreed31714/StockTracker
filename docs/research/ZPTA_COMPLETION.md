# ZPTA paper research integration

Owner: Codex. Approval: Brian's “Make it happen—through verified paper operation.”
Tracked in TradingOps #5; migration acceptance #2 remains PENDING.
Baseline: e002edcc5c97c5db7066d0a2039cbffb5c911a00.

PR #6 integrates the existing heads of #14, #39, #41 and #42 by merge ancestry.
Preserve those commits and historical reports; do not squash away their identities.
The old PR descriptions and dated research documents describe earlier checkpoints.
This document describes the integrated implementation, not a proven trading edge.

## Implemented scope

* #6: daily dip/recovery, fixed swing signals, hypothetical next-open scenarios,
  non-overlap, risk/friction stress, source revision checks and prospective snapshots.
* #14: first-receipt opportunity ledger and separate revisions; all entry block
  reasons; provider/data-age/volume diagnostics; receipt-anchored forward print
  outcomes; passive fifth Dip Recovery Hunter score; offline liquidity sensitivity
  and chronological audit of preserved October 21–27 observations. No new order route.
* #39: strict timestamped six-month close/noon/EOD study; missing noon prints
  remain unscored. No substitution of 12:30 bars for noon.
* #41: timestamp-aware sector/issuer headline join, original URLs and strict
  signal-day cutoff. Requires an independently timestamped and labeled corpus;
  absent corpus does not establish no-news days or predictive association.
* #42: prior-20-session RVOL, next-open gaps separated from entry returns,
  five-session train/holdout embargo, non-overlapping positions, deterministic
  weekday/trailing-volatility controls, week-cluster uncertainty and friction stress.

The existing four-model ensemble and shadow sizing/loss/entry/liquidity constants
are preserved. The fifth score is recorded only; it cannot drive `maybe_trade()`.
Forecast due times now start at receipt, preventing a delayed bar from creating an
already-expired forecast. Print references remain distinct from executable prices.
Full OHLCV, broker quote depth and historical receipt timestamps cannot be invented.

## Reproduction and tests

```
python -m unittest discover -s tests -p "test_zpta_*.py" -v
python -m infrastructure.registry_contract
python -m analysis.zpta_validation_bundle --daily PRIVATE_DAILY.csv --legacy-db PRIVATE_PAPER.sqlite3 --output PRIVATE_REPORT.json
python -m analysis.zpta_down_streak_noon_study --out PRIVATE_OUTPUT_DIRECTORY
python -m analysis.zpta_quantum_headline_join --prices PRIVATE_COMPARISON.csv --headlines VERIFIED_HEADLINES.csv --out PRIVATE_OUTPUT_DIRECTORY
```

CI runs deterministic tests on Windows and Linux without broker credentials.
The optional public-history job explicitly distinguishes fetch failure from test
success. No green check certifies market data or Windows activation.

The first integration CI reproduced the historical stale READY conflict for
P-STOCK-20261116-01. It is explicitly recorded SUPERSEDED by the existing -02
request (introduced in main 2a2dbd0 / PR #46), with original approval and SHA
unchanged. Existing local processing/active-release receipts support that sequence
but remain UNVERIFIED for runtime. No gate is weakened or new deployment requested.

The November 24 local research run obtained 501 daily bars, and 128 daily/717
hourly bars for the six-month study. No exact-noon bar was available. The preserved
October replay contains 16 sparse delayed-feed observations. Corporate actions,
original first receipts, OTC bid/ask depth and complete headline coverage remain
unverified. The validation bundle refuses promotion and executable-return claims.
These are data-coverage findings, not code work silently deferred after merging.

## Host adoption and acceptance

Only the existing supervised StockTracker paper trader imports the passive observer.
No competing ZPTA process or new scheduled sender is installed. Local artifacts:
`ZPTA_LOG_ROOT/research.sqlite3` and `research_latest.json`; default location
`momentum_logs/zpta/`, ignored by Git. Preserve all preexisting SQLite/state files.

Before adoption: exact-head CI and source review; verify remote main, clean local
source, paper-only source/config, current process identity/CWD, outside market/review
blackout and unrelated service baselines. Use the existing scoped activation helper
only after preflight; it targets one identified StockTracker trader and leaves the
supervisor responsible for replacement. Never bypass a failed activation guard.

After adoption, verify the replacement OS process and module-load receipt against
the approved hashes, then multiple genuine cycles and new local research output.
Receipt hashes are local self-reports, not independent memory/dependency attestation.
Report safe blocked/no-new-bar behavior honestly; synthetic tests are not paper fills.
Actual forward/session evidence remains pending until real subsequent data arrives.
The existing daily EOD equity/activity report and sole Pushover sender are preserved.

## Rollback

Preserve the pre-adoption source SHA, process/task baseline and private state backup.
Revert this integration through a checked PR, sync only the verified source, and
use the same scoped paper restart preflight. Keep the new research ledger read-only
for audit; never delete historical paper state, reset capital or reverse real records.
No live trading, changed risk limits, Helius changes or legacy-agent retirement.
