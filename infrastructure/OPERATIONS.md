# StockTracker infrastructure architecture and operations contract

## Windows host attestation recovery and release verification (October 22, 2026)

The `stocktracker-host-status` branch provides **sanitized, Windows-origin, read-only host evidence** independent of the `main` code branch. It does not authenticate an in-memory trader code digest or Alpaca execution correctness. Treat `main` CI, GitHub deployment requests and source synchronization as separate from Windows activation.

The initial host publication on October 20 used Windows text-mode stdin for `git mktree`, which translated LF to CRLF and inadvertently created a literal `status.json\r` filename. A successful push did **not** make a readable `status.json` at the expected GitHub path. The replacement publisher sends **bytes** to Git, parses NUL-terminated tree entries, allows exactly the single-file legacy branch for a non-force fast-forward repair and rejects any unrelated remote content. Never force-push or delete the attestation branch to repair this.

The attestor invalidates the old publication cache once, then refreshes unchanged healthy/failed observations at most once every six hours while the source is verified synchronized and local Git credentials work. Its report contains only a timestamp, Git SHA, attestation state, stable-process and dated post-sync EOD flags, and explicitly false flags for unverified in-memory/broker details; no PIDs, command lines, balances, symbols, credentials, or raw exception texts. A missing/stale status is **not** proof of a running or stopped Windows service.

The supervisor now enumerates Python processes only and requires bounded exact script names for **StockTrader**, **Geo Feed**, **Dashboard**, and **StockTracker deployment agent**. This avoids confusing other processes, backup filenames, shell commands, and the CryptoTracker agent. Windows process discovery failure must fail closed rather than trigger extra starts/restarts.

**Safe host adoption:** After the PR is merged and all CI checks pass, validate on Windows that the repo is clean and fast-forward synchronized, the active trader/Geo Feed/Dashboard and both projects have preserved identity, and no approved unprocessed request would accidentally run. A running deployment agent must be independently reloaded **agent-only** to import the new attestation publisher. Do **not** create a supervisor broad restart request or touch the paper trader, Geo Feed, dashboard or CryptoTracker. The already-running supervisor also retains its old in-memory matching logic until separately and safely reloaded. Never claim a GitHub merge reloads either process.

Confirm `stocktracker-host-status/status.json` has a normal filename and an observation later than the adoption, `git_head` matches expected main, process samples advance to `HOST_PROCESSES_STABLE_SOURCE_ONLY`, and a successful *post-sync* scheduled daily review subsequently advances to `EOD_EXECUTION_VERIFIED`. For `P-STOCK-*` approval changes, cross-check local `deploy/state/processed_requests.json`, active manifest, exact release file blobs, CI, release preflight, process start times and post-release reports. Preserve **PAPER ONLY** and all existing risk controls; never auto-promote research or infer profitability from process health.


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

Only the **exact positively identified v1.10 StockTracker paper-trader PID** may be stopped. The existing running supervisor must restore that trader; this tool **never creates a competing second trading process**, never restarts geo/dashboard/agent/supervisor, never touches CryptoTracker, and refuses weekday activation from 06:30–13:40 Pacific (PDT/PST). It requires a clean, fully synced Git HEAD, valid infrastructure registry, paper-only source markers, working review retry tests, an idle review, unique trader identity verified by its executed absolute script path, a matching supervisor PID/start-time record, or an OS-observed StockTracker working directory combined with a matching process creation time for a relative script, and all ten expected project processes observed. It aborts without a stop if any precondition is ambiguous.

The 2026-10-19 host audit identified the trader as PID 34140 with `RELATIVE_TRADER_SCRIPT_NO_PATH_AUTHORITY` and no supervisor launch record. An upgraded activation guard now uses the OS process working directory and creation timestamp through `psutil` to verify such cases; the repository working directory and the recorded Windows process start time **must both match** or activation stays blocked. The diagnostic `python -m infrastructure.diagnose_trader_activation` reports the read-only category `process_cwd_evidence` (e.g. MATCHED, PSUTIL_NOT_INSTALLED, CWD_ACCESS_UNAVAILABLE, FOREIGN_WORKING_DIRECTORY) without echoing paths or credentials. Install `psutil>=5.9,<8` into the Windows interpreter used by StockTracker if missing; do not skip or bypass the guard. Passing GitHub Windows tests is not evidence the host interpreter has this dependency.

The tool polls for the replacement trader, then observes its PID for 65 seconds and compares all other StockTracker and CryptoTracker service PIDs. Its **local ignored** `deploy/state/review_repair_activation.json` receipt records the results without secrets. If the existing supervisor fails to restart the trader, it reports **RESTART_NOT_OBSERVED** and stops; it deliberately does *not* launch a second trader or blindly restart other components. The previous Git trader revision remains available for a separately controlled rollback, but **automatic rollback is not yet implemented**.

A verified paper-trader process restart **does not verify** the next successful OpenAI review, an unattended task run, broker paper-order state, or sustained trading correctness. Require the next genuine market-close report, successful scheduled task result, and a separate restart/reboot recovery test before marking the release VERIFIED.

## Incident / dependency protocol

When a status is incorrect, compare its data source with producer output before restarting. Verify PID start time and process ownership before stopping anything. Stop only the affected component with minimal privilege. Do not restart healthy trading engines to repair a dashboard or auxiliary feed. When a test fails, capture the precise failing path, build log and expected runtime evidence; never suppress the failure to make CI green.

## Updating the contract

Any change that adds, renames, retires, or reconnects a component must update `registry.json`, source ownership, dependencies, data/provider contracts, negative tests, and this document in the same release. The registry is checked on every main-branch change affecting infrastructure and on deployment preflight. CI branch-protection settings must be verified separately; a GitHub Action cannot guarantee branch blocking without repository rules.


## Sanitized EOD summary and offline missed-opportunity research (October 19, 2026)

**Scope:** This is a reviewed-code mechanism, NOT proof of Windows-host publication, runtime freshness, or a paper-trader deployment. The previously configured external \`STOCKTRACKER_RUNTIME_ROOT\` stays authoritative for all raw data, positions, proposals, detailed logs, and account state.

When external runtime reports exist, \`sync_proposals_to_git.py\` calls \`safe_summary_publish.py\` after successful local model review and proposal registration. It exports **only** an explicitly allowlisted JSON snapshot to \`analysis/performance/sanitized_latest.json\` and \`analysis/performance/sanitized_daily/YYYY-MM-DD.json\`: review date, paper-only/data-quality status, decision and order counts, realized P/L, win/loss counts, limited shadow-sample counts, and sanitized proposal IDs/statuses. It deliberately excludes account/equity details, ticker positions, raw data, provider errors, candidate features, proprietary proposal prose, and logs. A private Git repository is still a data destination: review allowed fields before granting broader access.

Publication refuses an unexpected Git branch, staged/non-allowlisted working changes, a stale review, malformed inputs or non-fast-forward push. It never pulls/rebases/resets, restarts a process, or changes the trading engine. A refused/failed publication propagates to the review-guard error handling rather than falsely declaring Git reporting complete. \`STOCKTRACKER_SANITIZED_GITHUB_PUBLISH=0\` disables publication (used in isolated CI smoke tests); with an external runtime configured and this variable unset, publishing is enabled **after** host synchronization of the reviewed code.

**A successful GitHub CI check is not host deployment.** Confirm the post-close task's next result, summary JSON date, single-day Git commit, absence of raw files in staged or committed changes, Pushover EOD status, and repeated host review success. Clean checkout, Git author configuration and credential access are required. If the host has recovery stashes or working-tree changes, stop and reconcile outside trading hours; do not force-clean the repository or disable safety checks.

\`python -m research.shadow_opportunity_audit --evidence analysis/evidence/YYYY-MM-DD\` computes per-candidate 5/15/30/60-minute observed-price outcomes and sampled-close fixed versus trailing exit counterfactuals **without broker/network access**. It is currently an optional offline RESEARCH tool, not a live trading configuration or evidence that any threshold should be modified. One-minute decisions cannot reconstruct intrabar fills or true ATR; add OHLC price data, verified order fills, slippage and independent out-of-sample dates before evaluating exit changes. Return-on-portfolio target remains **NOT MEASURABLE** until trustworthy beginning/ending account equity snapshots are recorded.


## Automated Windows activation attestation (October 19, 2026)

The approved StockTracker deployment-agent loop can now call the **read-only** \`infrastructure/windows_activation_attestation.py\` probe after its ordinary clean Git fast-forward and request processing. A successfully completed EOD batch also runs one bootstrap probe without changing the EOD result code. This does **not** restart, stop, or launch trading processes. Existing in-memory Python agents do not hot-reload merely because their source file changed.

A local-only, ignored \`deploy/state/activation_attestation.json\` receipt is updated atomically. It distinguishes:

- \`UNVERIFIED\`: no positive Git-sync/source-integrity evidence.
- \`CODE_SYNCED_RUNTIME_UNVERIFIED\`: correct source bytes are on the Windows disk, but process provenance is missing or inconsistent.
- \`CODE_SYNCED_PROCESS_OBSERVED\`: one or two observations of expected processes; insufficient to claim sustained stability.
- \`HOST_PROCESSES_STABLE_SOURCE_ONLY\`: **three** observations, at least 20 seconds apart, of the same positively identified StockTracker supervisor, agent, paper trader, geo feed, and dashboard **including Windows creation time**, plus matched trader/geo/dashboard script filenames. This proves *host process observations*, **not** that Python reloaded a changed source file or that a broker trade succeeded.
- \`EOD_EXECUTION_VERIFIED\`: additionally, the local post-close guard has completed *after this Git revision was first witnessed*, and same-date model-review and evidence artifacts agree. This validates the EOD review path for that date, **not** strategy profitability, broker fills, restart recovery or an in-memory trading-engine source digest.

The receipt intentionally stays on the host. A private GitHub commit and green CI do not prove the host is synchronized; the assistant must not claim Windows activation before receiving host evidence. The verifier publishes neither account credentials, raw command lines, trade logs nor broker account data.

The agent sends Pushover when a **new commit first synchronizes** and when the state becomes \`EOD_EXECUTION_VERIFIED\`. Notification receipt says \`API_ACCEPTED\` only if Pushover returned HTTP 200 and JSON status 1; device delivery is still not guaranteed. No notification is repeatedly sent while its status key is unchanged. Missing local Pushover credentials leave \`UNCONFIRMED\` and are not described as a successful push.

**Bootstrap limitation:** The already-running agent must be restarted/reloaded once through a separately approved, safely attributed host action to adopt its new polling hook. Do **not** use a broad release request or restart the trader just to enable this observation hook. The new post-close batch additionally performs one read-only attempt automatically at its next actual execution after Git synchronization; full three-cycle automatic attestation requires the updated agent running. If the agent cannot safely be restarted, record status as unverified rather than inventing activation. The one-shot command is:

\`\`\`powershell
python -m infrastructure.windows_activation_attestation --notify
\`\`\`

This command is read-only with respect to trading processes, scheduled tasks, git state, and broker orders; it only creates the ignored receipt and optionally sends a Pushover status notice. To pin a specific checkout during diagnosis, add \`--expect <full-current-HEAD-sha>\`. Do not use a report from another PC or an old date as proof. Windows task/host recovery verification remains independent.


### Independently readable host signal (dedicated private branch)

The host attestor additionally publishes *allowlisted status only* to the dedicated private Git branch \`stocktracker-host-status\`, file \`status.json\`. This avoids requiring the user to run local diagnostics or forward Pushover screenshots for every release. It does not publish full process inventories, raw task output, PIDs, positions, order IDs, provider details, or credentials. It cannot attest a stopped/offline Windows PC: the timestamp on the last signal is part of the evidence, and a stale signal must be treated as stale.

Publication is transition-driven (new code HEAD, process-stability change, post-sync EOD evidence) rather than every minute. It uses Git objects on the existing Windows repository without touching the checked-out branch or files, and pushes **only** a non-force update to \`refs/heads/stocktracker-host-status\`. An unrelated or unexpected pre-existing status branch is rejected, not overwritten. Concurrent non-fast-forward changes fail closed; no \`git pull\`, force push, reset, checkout or trader/supervisor restart is performed.

If the host Git remote is read-only, credentials are unavailable, or the repo is not on \`main\`, the Pushover/local receipt mechanisms can continue, but remote status remains \`UNCONFIRMED\`; investigate through established safe host processes. Optional \`STOCKTRACKER_ATTESTATION_REMOTE_ENABLED=0\` disables publishing without disabling local checks. As with the local attestor, the *currently running* agent must load the updated code before unattended transition polling can begin. The next successful post-close batch also invokes a single fresh on-disk probe when synchronized.

To inspect remotely via the connected GitHub repository, read the \`stocktracker-host-status\` branch's \`status.json\` and check that its \`observed_at_utc\`, \`git_head\`, \`state\`, and \`post_sync_eod_verified\` match the intended release and period. Do not confuse this with proof of an in-memory trading-engine code digest, a paper-broker fill, or reboot recovery: the payload marks both separately as **not verified**.
