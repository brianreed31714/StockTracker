# StockTracker Project Context

## Purpose
StockTracker is a PAPER-ONLY multi-asset momentum research/trading system. It must remain paper-only unless the user explicitly redesigns the project outside this agentic workflow.

## Configured fallback (not live deployment proof)
- Trader fallback from `.env.config`: `momentum_trader_v1_9_zpta_shadow.py`
- Geo/oil feed fallback: `xom_geo_feed_v1_1_agentic.py`
- Dashboard fallback: `momentum_dashboard_v1_3_agentic.py`
- Historical observed Windows trader on 2026-10-18: `momentum_trader_v1_10_runtime_audit.py` (revalidate on host).
- Local `deploy/state/active_release.json` and the [infrastructure registry](infrastructure/registry.json) govern code resolution and dependencies; do not infer current runtime from this document.

## Tradable universe
Configured by `TRADE_SYMBOLS` in `.env.config`. Current tradable baseline:
XOM, WMT, AMZN, AAPL, NVDA, TSLA, NBIS, SPY, QQQ, GLD.

SHADOW-only research symbols: XLF, FAS, FAZ. These are not in `TRADE_SYMBOLS`.

ZPTA is an integrated SHADOW-only OTC specialist. It is not in `TRADE_SYMBOLS`, never reaches the Alpaca order-submission path, and uses an isolated virtual sleeve while writing evidence into the StockTracker database and daily review.

## Architecture
- Alpaca paper account executes simulated orders.
- Trader scores technical momentum plus cross-market context and VIX regime.
- XOM receives a bounded geo/oil adjustment from `geo_feed.json`.
- GLD receives a smaller geo adjustment.
- Trader writes SQLite audit data, daily CSVs, and dashboard state.
- Dashboard is read-only.
- Geo feed classifies recent oil/geopolitical RSS items with OpenAI and never places orders.
- EOD reporting uses Pushover.
- Runtime databases, mutable state, secrets, and unsanitized logs stay local/ignored.
- Five minutes after the actual Alpaca session close, including early closes, the trader starts the idempotent review pipeline.
- Every review publishes sanitized row-level supporting tables, state/feed snapshots, a 500-line geo-log tail, SHA-256 hashes, and integrity checks under `analysis/evidence/YYYY-MM-DD/`.
- Durable proposals, sanitized evidence, and performance summaries are committed to GitHub.

## Agentic workflow
1. Runtime processes accumulate paper-trading evidence.
2. At actual market close + 5 minutes, `run_daily_model_review.bat` builds the daily metrics bundle.
3. `publish_supporting_evidence.py` exports every supporting table and injects full-row integrity results into the review input.
4. `daily_model_review.py` analyzes the full-table summaries, integrity results, and model metrics and drafts proposals.
5. `proposal_registry.py` assigns stable IDs such as `P-STOCK-20260927-01`.
6. `sync_proposals_to_git.py` pushes sanitized evidence, proposals, and performance summaries to GitHub.
7. In ChatGPT, the user can say:
   - "Review today's StockTracker proposals"
   - "Approve P-STOCK-YYYYMMDD-NN"
   - "Decline P-STOCK-YYYYMMDD-NN"
8. Approved implementation changes are committed to GitHub and a request is written to `deploy/requests/`.
9. `stocktracker_deployment_agent.py` validates protected capabilities, updates the local repo, restarts approved components, and records local deployment state.
10. `stocktracker_supervisor.py` watches the deployment agent, trader, geo feed, and dashboard and restarts missing processes.

## ZPTA integrated shadow sleeve
- `zpta_specialist_v0_1.py` is imported and invoked by the active StockTracker trader during regular-session cycles.
- Competing models: breakout continuation, momentum pullback, VWAP reclaim, and exhaustion/exit risk.
- Every forecast is resolved at 5, 15, and 60 minutes and stored in `zpta_predictions`.
- Virtual entries/exits are stored in `zpta_shadow_trades`; no broker order function exists in the specialist.
- OTC sparsity is handled with clock-time lookbacks rather than assuming each observed print represents one minute.
- Alpaca OTC data is attempted first; delayed Yahoo chart data is permitted only for shadow research fallback.
- Promotion requires at least 20 sessions and 300 resolved forecasts plus positive post-slippage expectancy, profit factor >=1.25, drawdown <=8%, and explicit approval before any live redesign.

## Protected deployment invariants
Future trader releases must preserve:
- PAPER_ONLY = True
- Alpaca TradingClient configured with paper=True
- split `.env.config` + local `.env` loading
- configurable Alpaca market-data feed
- portfolio/trade/daily-loss limits
- XOM geo integration
- stock EOD reporting
- actual-session-close + five-minute daily evidence publication and analysis

Future geo-feed releases must preserve:
- no order submission/trading client
- split config/secret loading
- bounded materiality/confidence classification
- atomic local feed output

Future dashboard releases must remain read-only.

## Performance artifacts
- Local/raw: `analysis/daily/YYYY-MM-DD/` (ignored)
- Durable/sanitized row-level evidence: `analysis/evidence/YYYY-MM-DD/`
- Durable/sanitized summary: `analysis/performance/latest.json`, `analysis/performance/latest.md`
- Proposals: `analysis/proposals/`

A fresh ChatGPT session should use this file plus `analysis/performance/latest.*` and `analysis/proposals/REVIEW.md` to understand the project.


## Shadow market research
- Broad market regime: SPY 50/200-day trend, SPY 20-day momentum, QQQ 200-day confirmation, and VIX.
- Defensive benchmark in RISK_OFF: SGOV (simulation/research only).
- Financial leverage research: XLF is the underlying financial-sector direction signal; FAS is the bullish 3x research candidate; FAZ is the bearish 3x research candidate.
- FAS/FAZ are SHADOW only. They are not currently paper-traded.
- Candidate signals record 5/15/30/60-minute forward outcomes before any future execution proposal.


## Market-aware runtime
- Full one-minute market scanning runs only during the regular session after a 20-minute opening warmup.
- When the market is closed, the trader sleeps instead of requesting every symbol once per minute.
- Premarket intelligence begins 30 minutes before the next regular-session open and refreshes at 30/20/10/5/1 minutes before the open.
- Premarket inputs: SPY, QQQ, XLF, FAS, FAZ gaps/momentum, VIX, and the existing geo/headline feed.
- Social sentiment is explicitly marked UNAVAILABLE until a real source is configured; it is never inferred or fabricated.
- The latest premarket bias can contribute a bounded +/-5 context adjustment during the first 60 regular-session minutes.
- No premarket orders are submitted.

## Approved remediation work (2026-10-09)
The user approved implementing proposals P-STOCK-20261008-01 through -06, plus NBIS runtime verification, independent methodology scorecards, equity curve/return attribution, and unattended daily health assessment. Approval does not imply code deployed. Preserve paper-only, risk limits, and shadow isolation. Implementation agents should prioritize restoring empty premarket and financial leverage datasets, ZPTA zero shadow trades, funnel and missed-opportunity outcome instrumentation, ATR exit counterfactuals, geo deduplication, NBIS env/runtime reconciliation, and daily methodology attribution. Verify tests, publish evidence and deployment status. ChatGPT daily external review is scheduled separately; Windows review/supervisor remain necessary.
