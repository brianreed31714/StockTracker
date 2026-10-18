# StockTracker infrastructure architecture and operations contract

This file describes the **repository design**, not a claim that every service is running on the Windows trading PC. The machine-readable authority for code relationships is [registry.json](registry.json). Actual runtime evidence is created by `runtime_inventory.py` on that PC only. The runtime manifest, credentials, databases and logs remain local.

## Component boundaries

| Component | Entrypoint or resolution | Process owner | Responsibility |
|---|---|---|---|
| Supervisor | `stocktracker_supervisor.py` | Scheduled task: StockTracker Supervisor | Starts/restarts services |
| Deployment agent | `stocktracker_deployment_agent.py` | Supervisor | Git sync, request validation, release records |
| Trader | Local active manifest; configured fallback `momentum_trader_v1_9_zpta_shadow.py` | Supervisor | Alpaca paper trading / shadow models |
| Geo feed | `xom_geo_feed_v1_1_agentic.py` | Supervisor | Read-only news classification and `geo_feed.json` |
| Dashboard | `momentum_dashboard_v1_3_agentic.py` | Supervisor | Read-only paper and research status |
| Daily review | `run_daily_model_review.bat` | StockTracker Daily Review task and trader post-close path | EOD proposals and evidence |

## Provider and data dependencies

`registry.json` lists outbound providers, whether they are paper/read-only, local evidence files, producer/consumer relationships, and freshness semantics. A component may be *alive but not healthy* or *invisible to Windows command-line inspection but writing healthy heartbeats*. We test these separately.

## Existing knowledge gaps (do not guess)

- The tracked fallback trader is **v1.9**; prior documentation mentions **v1.4** and **v1.8**. User-supplied October 18 process evidence showed **v1.10**, but this is not a live attestation.
- Local `deploy/state/active_release.json` (not GitHub README) supplies deployed component filenames and may differ from the fallback.
- The Windows scheduled review task is configured for weekdays at 1:30 PM local in the installer. Actual installation/last run require host inventory.
- Geo feed can be quiet when news is quiet; missing fresh news is not automatically a stopped process.
- The post-close review also has a trader-initiated path; these mechanisms require duplicate-run protection, not an invented single scheduler assumption.

## Non-negotiable operating constraints

The currently approved StockTracker trading path is paper-only: trader code must contain `PAPER_ONLY = True`, create `TradingClient(..., paper=True)`, and retain risk limits. ZPTA and leverage research remain shadow-only; no promotion to live execution is authorized.

## Local host inventory (read-only)

For a **single** side-effect-free inventory of both repositories, once the new files have synced to the PC, run from either repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infrastructure\audit_both_projects.ps1
```

This helper intentionally does not run Git commands, stop services or create tasks; it reports if either repository lacks the new files. The two local reports are written only to each repository's ignored `deploy/state/` folder.

For project-specific inspection, after a clean fast-forward to the exact expected `origin/main`, run from the respective repository root in PowerShell:

```powershell
python -m infrastructure.registry_contract --local-safety
python -m infrastructure.runtime_inventory --write-local
```

The latter inspects Windows scheduled-task metadata, non-secret Python process identity and start time, local active manifest, HEAD commit, and declared heartbeat files. The output `deploy/state/infrastructure_inventory.json` is **gitignored**, never auto-committed or sent to GitHub. It deliberately never writes raw command lines, usernames, secret values, or wallet addresses. If process command lines are hidden, PID attribution requires a matching supervisor launch record *and* start time; otherwise the identity stays UNKNOWN.

A green GitHub Action alone establishes **code/test validation only**, not live deployment. The host inventory is an observation, not proof of successful trading or sustained service health.

## Local release preflight and safety gate

Both local deployment agents invoke `release_preflight()` from [registry_contract.py](registry_contract.py) in `validate_request` before calling `stop_active` or issuing a controlled restart. The gate rejects:
- Missing/invalid/inconsistent component registry or declared source files;
- Missing configured entrypoints or invalid component script families;
- Missing trader paper-only markers and forbidden locally enabled safety flags;
- Requests naming undeclared components or duplicate components;
- Syntax errors in proposed release modules and their declared dependencies.

The pre-existing deployment agents **also** guard component-specific capabilities and Git release blob identity. A deployment request must be explicitly approved before any process replacement; a green test run is not approval.

Both deployment agents use explicit `git fetch origin main` + `git merge --ff-only origin/main`, rather than ambiguous `git pull`. A non-fast-forward or unexpected local code change must stop deployment.

## Verification discipline / exit criteria

1. **Plan:** identify source owner and downstream consumers with `change_impact()`; note unowned Python modules explicitly.
2. **Test:** validate architecture and paper safety; run Python negative tests on Linux and Windows; run project-specific regression tests; no credentials in CI.
3. **Approve:** code review and explicit release request; do not auto-enable live trading or paid feeds.
4. **Deploy:** local agent verifies source blob and registry before touching a running process; preserve previous manifest and rollback plan.
5. **Verify on the host:** compare manifest/commit and start times, scheduled task and component identity, dashboard status, and required data-feed heartbeat. Require repeated successful observation after startup (not just one good JSON report).
6. **Report:** declare "code committed", "CI validated", "host observed", or "release verified" separately. Never collapse those into "deployed successfully" without host evidence.

Deployment agents now record `verification_status=UNVERIFIED` and notify that supervisor startup was acknowledged, **not** that sustained health was proven. Invalid unchanged release requests are locally quarantined as `VALIDATION_FAILED` rather than retried repeatedly.

The repository does **not yet** contain a fully proven autonomous deployment-attestation loop for every service. Treat any unresolved runtime verification as `UNVERIFIED`, not success. In particular, the existing supervisor success handshake primarily verifies processes, not three independent healthy operating cycles.

## Incident / dependency protocol

When a status is incorrect, compare its data source with producer output before restarting. Verify PID start time and process ownership before stopping anything. Stop only the affected component with minimal privilege. Do not restart healthy trading engines to repair a dashboard or auxiliary feed. When a test fails, capture the precise failing path, build log and expected runtime evidence; never suppress the failure to make CI green.

## Updating the contract

Any change that adds, renames, retires, or reconnects a component must update `registry.json`, source ownership, dependencies, data/provider contracts, negative tests, and this document in the same release. The registry is checked on every main-branch change affecting infrastructure and on deployment preflight. CI branch-protection settings must be verified separately; a GitHub Action cannot guarantee branch blocking without repository rules.
