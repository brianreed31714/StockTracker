# StockTracker

Paper-only multi-asset momentum research system, geo/oil feed, shadow
research models, review pipeline, supervisor and read-only dashboard.

**Canonical infrastructure contract:** [registry](infrastructure/registry.json)
and [architecture / operations guide](infrastructure/OPERATIONS.md).

The tracked configuration currently uses `momentum_trader_v1_9_zpta_shadow.py`
as a **fallback**; a Windows runtime observation on October 18, 2026
showed `momentum_trader_v1_10_runtime_audit.py`. Neither fact replaces the
local `deploy/state/active_release.json` and read-only process inspection
for the currently active version.

Research resources:
- [Project context](STOCKTRACKER_CONTEXT.md)
- [Agentic setup](AGENTIC_SETUP.md)

Paper-only protection: `PAPER_ONLY = True` and
`TradingClient(..., paper=True)`. ZPTA and leverage sleeves remain shadow
research unless explicitly redesigned and approved.

From the Windows repository folder, after an explicit clean fast-forward:

```powershell
python -m infrastructure.registry_contract --local-safety
python -m infrastructure.runtime_inventory --write-local
```

Green GitHub Actions validate code and contracts, not the actual Windows
runtime. Avoid restarting a healthy trader to repair an auxiliary feed.
