# StockTracker Project Context

## Purpose
StockTracker is a PAPER-ONLY multi-asset momentum research/trading system. It must remain paper-only unless the user explicitly redesigns the project outside this agentic workflow.

## Active baseline
- Trader: `momentum_trader_v1_7_financial_leverage_shadow.py`
- Geo/oil feed: `xom_geo_feed_v1_1_agentic.py`
- Dashboard: `momentum_dashboard_v1_3_agentic.py`

## Tradable universe
Configured by `TRADE_SYMBOLS` in `.env.config`. Current tradable baseline:
XOM, WMT, AMZN, AAPL, NVDA, TSLA, SPY, QQQ, GLD.

SHADOW-only research symbols: XLF, FAS, FAZ. These are not in `TRADE_SYMBOLS`.

## Architecture
- Alpaca paper account executes simulated orders.
- Trader scores technical momentum plus cross-market context and VIX regime.
- XOM receives a bounded geo/oil adjustment from `geo_feed.json`.
- GLD receives a smaller geo adjustment.
- Trader writes SQLite audit data, daily CSVs, and dashboard state.
- Dashboard is read-only.
- Geo feed classifies recent oil/geopolitical RSS items with OpenAI and never places orders.
- EOD reporting uses Pushover.
- Runtime databases, logs, state, secrets, and raw daily analysis stay local/ignored.
- Durable proposals and sanitized performance summaries are committed to GitHub.

## Agentic workflow
1. Runtime processes accumulate paper-trading evidence.
2. `run_daily_model_review.bat` builds a sanitized daily evidence bundle.
3. `daily_model_review.py` analyzes the evidence and drafts proposals.
4. `proposal_registry.py` assigns stable IDs such as `P-STOCK-20260927-01`.
5. `sync_proposals_to_git.py` pushes proposals and performance summaries to GitHub.
6. In ChatGPT, the user can say:
   - "Review today's StockTracker proposals"
   - "Approve P-STOCK-YYYYMMDD-NN"
   - "Decline P-STOCK-YYYYMMDD-NN"
7. Approved implementation changes are committed to GitHub and a request is written to `deploy/requests/`.
8. `stocktracker_deployment_agent.py` validates protected capabilities, updates the local repo, restarts approved components, and records local deployment state.
9. `stocktracker_supervisor.py` watches the deployment agent, trader, geo feed, and dashboard and restarts missing processes.

## Protected deployment invariants
Future trader releases must preserve:
- PAPER_ONLY = True
- Alpaca TradingClient configured with paper=True
- split `.env.config` + local `.env` loading
- configurable Alpaca market-data feed
- portfolio/trade/daily-loss limits
- XOM geo integration
- stock EOD reporting

Future geo-feed releases must preserve:
- no order submission/trading client
- split config/secret loading
- bounded materiality/confidence classification
- atomic local feed output

Future dashboard releases must remain read-only.

## Performance artifacts
- Local/raw: `analysis/daily/YYYY-MM-DD/` (ignored)
- Durable/sanitized: `analysis/performance/latest.json`, `analysis/performance/latest.md`
- Proposals: `analysis/proposals/`

A fresh ChatGPT session should use this file plus `analysis/performance/latest.*` and `analysis/proposals/REVIEW.md` to understand the project.


## Shadow market research
- Broad market regime: SPY 50/200-day trend, SPY 20-day momentum, QQQ 200-day confirmation, and VIX.
- Defensive benchmark in RISK_OFF: SGOV (simulation/research only).
- Financial leverage research: XLF is the underlying financial-sector direction signal; FAS is the bullish 3x research candidate; FAZ is the bearish 3x research candidate.
- FAS/FAZ are SHADOW only. They are not currently paper-traded.
- Candidate signals record 5/15/30/60-minute forward outcomes before any future execution proposal.
