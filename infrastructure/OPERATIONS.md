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

## ZPTA shadow specialist dashboard (October 19, 2026)

The read-only `momentum_dashboard_v1_3_agentic.py` now uses `zpta_dashboard_support.py` to classify and explain the *actual* ZPTA error recorded in `dashboard_state.json`, without printing raw provider exceptions or credentials. The error remains visible until the specialist recovers. The last stored quote includes its original timestamp and an explicit **historical, not live** label; no stale market data is substituted into live signal metrics.

ZPTA resolved forecast detail is now grouped by the **Eastern Time date of resolution**, model, and horizon, with correct per-date sample counts, accuracy and average returns. The former lifetime aggregates are preserved under an **All-time summary** tab. The dashboard SQLite connections use read-only mode with explicit closure to avoid Windows file-lock leaks and accidental database creation. These changes do not edit the shadow specialist, the paper trader, its process, the source database, or the provider credentials.

**Outstanding:** A user screenshot of `Status: ERROR` proves the specialist reported an exception, but does not establish its root cause. The underlying provider/data or specialist exception can only be diagnosed from the Windows-local `zpta_shadow.error` state or local logs. Code CI and visible dashboard improvements do not establish live data-feed recovery. A normal Git auto-sync may refresh Streamlit files; no `READY_TO_DEPLOY` request or broad restart is authorized for a presentation-only repair.

## Provider and data dependencies

`registry.json` lists outbound providers, whether they are paper/read-only, local evidence files, producer/consumer relationships, and freshness semantics. A component may be *alive but not healthy* or *invisible to Windows command-line inspection but writing healthy heartbeats*. We test these separately.

## Existing knowledge gaps (do not guess)

- The tracked fallback trader is **v1.9**; prior documentation mentions **v1.4** and **v1.8**. User-supplied October 18 process evidence showed **v1.10**, but this is not a live attestation.
- Local `deploy/state/active_release.json` (not GitHub README) supplies deployed component filenames and may differ from the fallback.
- The Windows scheduled review task is configured for weekdays at 1:35 PM Pacific in the installer. Existing installed tasks must be updated separately. Actual installation/last run require host inventory.
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

## Pacific market/review timing (October 19, 2026)

The Windows StockTracker host is on Pacific Time. The weekday safety blackout for **scoped paper-trader activations** is now **06:30–13:40 Pacific** (inclusive of the opening boundary and exclusive of the 13:40 boundary), using `America/Los_Angeles` to handle PDT and PST. Weekend activation is not time-blocked, but all process ownership and paper safety checks remain mandatory.

Both reporting paths now target **13:35 Pacific (16:35 Eastern)** on regular weekdays:

- Dedicated Stock EOD Pushover notification: `PUSHOVER_STOCK_EOD_HOUR=16`, `PUSHOVER_STOCK_EOD_MINUTE=35`.
- AI review and sanitized evidence: `POST_CLOSE_REVIEW_DELAY_MINUTES=35` plus a 13:35 Pacific **minimum start** on shortened trading sessions. Alpaca's actual session close still controls market-calendar availability, and the shared retry guard prevents overlapping trader/scheduled-task attempts.

The installer `install_stocktracker_tasks.ps1` is updated for future installations but **must not be rerun** merely to change the existing task; it unregisters tasks and starts the supervisor. To change only the existing daily review task's trigger without touching any running services, use this from an authorized **Pacific-time Windows PowerShell** in the StockTracker repo:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infrastructure\apply_review_135.ps1
# After reviewing the output, explicitly apply just the weekday trigger:
powershell -NoProfile -ExecutionPolicy Bypass -File .\infrastructure\apply_review_135.ps1 -Apply
```

The helper fails closed if the task action or existing trigger is unexpected or if the task is running. It may require elevated Task Scheduler permissions. A changed GitHub installer alone does not change the already-installed Windows task. The running trader also needs a **separately controlled restart after 13:40** to load new in-memory EOD settings; code sync does not hot-reload the Python process. If the task starts after its scheduled minute because Windows was unavailable, it can run late; no guarantee of exactly 13:35 execution is possible without live task verification.

## Controlled review repair activation (local Windows only)

The committed review fix does **not** automatically modify an existing in-memory trader process. The existing deployment agent's `READY_TO_DEPLOY` path still uses a **whole-StockTracker** supervisor restart, and the already-running agent will not hot-reload its Python implementation. **Do not create a new READY_TO_DEPLOY request for this maintenance repair.**

A scoped activation utility is available at [activate_review_repair.py](activate_review_repair.py), with isolated tests on both Windows and Linux. On the Windows PC, from the **StockTracker** repository root:

```powershell
python -m infrastructure.activate_review_repair
```

The default performs read-only safety and ownership validation. After confirmation, this is the explicit operator-initiated action:

```powershell
python -m infrastructure.activate_review_repair --apply
```

Only the **exact positively identified v1.10 StockTracker paper-trader PID** may be stopped. The existing running supervisor must restore that trader; this tool **never creates a competing second trading process**, never restarts geo/dashboard/agent/supervisor, never touches CryptoTracker, and refuses weekday activation from 06:30–13:40 Pacific (PDT/PST). It requires a clean, fully synced Git HEAD, valid infrastructure registry, paper-only source markers, working review retry tests, an idle review, unique trader identity with absolute StockTracker path, and all ten expected project processes observed. It aborts without a stop if any precondition is ambiguous.

The tool polls for the replacement trader, then observes its PID for 65 seconds and compares all other StockTracker and CryptoTracker service PIDs. Its **local ignored** `deploy/state/review_repair_activation.json` receipt records the results without secrets. If the existing supervisor fails to restart the trader, it reports **RESTART_NOT_OBSERVED** and stops; it deliberately does *not* launch a second trader or blindly restart other components. The previous Git trader revision remains available for a separately controlled rollback, but **automatic rollback is not yet implemented**.

A verified paper-trader process restart **does not verify** the next successful OpenAI review, an unattended task run, broker paper-order state, or sustained trading correctness. Require the next genuine market-close report, successful scheduled task result, and a separate restart/reboot recovery test before marking the release VERIFIED.

## Incident / dependency protocol

When a status is incorrect, compare its data source with producer output before restarting. Verify PID start time and process ownership before stopping anything. Stop only the affected component with minimal privilege. Do not restart healthy trading engines to repair a dashboard or auxiliary feed. When a test fails, capture the precise failing path, build log and expected runtime evidence; never suppress the failure to make CI green.

## Updating the contract

Any change that adds, renames, retires, or reconnects a component must update `registry.json`, source ownership, dependencies, data/provider contracts, negative tests, and this document in the same release. The registry is checked on every main-branch change affecting infrastructure and on deployment preflight. CI branch-protection settings must be verified separately; a GitHub Action cannot guarantee branch blocking without repository rules.
