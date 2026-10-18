# StockTracker Agentic Setup

StockTracker is a PAPER-ONLY trading research system. The agentic workflow reviews paper-trading evidence, publishes human-readable proposals, accepts proposal approval in ChatGPT, and can deploy approved code/config updates through the local deployment agent.

## Managed processes (version resolution)

- Trader: `momentum_trader_v*.py` resolved from the **local active manifest** first; `.env.config` fallback currently names v1.9. Windows observation on 2026-10-18 showed v1.10.
- Geo feed: `xom_geo_feed_v1_1_agentic.py` (or the local active-manifest override).
- Dashboard: `momentum_dashboard_v1_3_agentic.py` (or the local active-manifest override).
- Deployment agent: `stocktracker_deployment_agent.py`.
- Supervisor: `stocktracker_supervisor.py`.

See [infrastructure registry](infrastructure/registry.json) and [operations contract](infrastructure/OPERATIONS.md) for source ownership, read-only inventory and enforced release preflight.

The deployment agent has regression guards that prevent a future release from silently removing PAPER-ONLY mode, portfolio/daily-loss controls, split config loading, geo-feed boundaries, or read-only dashboard behavior.

## One-time migration from the old StockTracker folder

Before starting the GitHub-based StockTracker, copy the existing LOCAL runtime data from the old working folder into this repository:

- `.env`
- `momentum_trader.sqlite3`
- `momentum_logs\`
- `dashboard_state.json`
- `geo_feed.json`
- `geo_feed_state.json`
- `geo_feed.log`
- `stock_eod_report_state.json` if present

These files are ignored by Git and must never be committed.

This preserves historical paper trades and gives the daily model-review agent useful evidence from the first run.

## Daily review

Manual:

```bat
run_daily_model_review.bat
```

Flow:

1. Pull latest GitHub changes.
2. Build `analysis/daily/YYYY-MM-DD/performance_input.json` locally.
3. Run the GPT-5.6 Sol model review.
4. Publish stable IDs such as `P-STOCK-20260927-01`.
5. Commit/push:
   - `analysis/proposals/`
   - `analysis/performance/latest.json`
   - `analysis/performance/latest.md`

Raw daily evidence remains local and ignored.

## ChatGPT commands

In a fresh ChatGPT conversation with GitHub connected:

```text
How is StockTracker performing?
```

```text
Review today's StockTracker proposals
```

Then approve or decline by stable ID:

```text
Approve P-STOCK-YYYYMMDD-NN
Decline P-STOCK-YYYYMMDD-NN
```

Approved changes are implemented in GitHub and a deployment request is placed under `deploy/requests/`.

## Local deployment agent

Start manually for testing:

```bat
python stocktracker_deployment_agent.py
```

The agent polls GitHub for `READY_TO_DEPLOY` requests, validates code and protected capabilities, then restarts only the components listed in the request.

Local deployment state is stored in ignored `deploy/state/`.

## Supervisor

Start manually:

```bat
python stocktracker_supervisor.py
```

It watches and recovers:

- Deployment Agent
- Trader
- Geo Feed
- Dashboard

## Windows auto-start + scheduled review

After manual testing succeeds, open PowerShell **as Administrator** and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\install_stocktracker_tasks.ps1
```

This creates:

- **StockTracker Supervisor** — starts 30 seconds after PIN login.
- **StockTracker Daily Review** — weekdays at 1:30 PM local Windows time, intended to be 4:30 PM Eastern / 30 minutes after normal market close.

No Windows account password is stored.

## Important safety invariant

This agentic system is intentionally PAPER ONLY. A future model proposal may improve the research/paper model, but the deployment guard will reject releases that switch Alpaca to live brokerage execution.
