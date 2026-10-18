# Infrastructure reliability backlog and evidence status

This is a failure register, not a statement that the runtime is broken at this instant.
Keep entries open until a **host** observation or an end-to-end test closes them.
The [machine registry](registry.json) models repository dependencies;
the [operations runbook](OPERATIONS.md) defines release gates.

| Priority | Defect / limitation | Evidence | Required closure |
|---|---|---|---|
| P0 | Windows host inventory not yet executed against these new registries | GitHub has no direct access to local `deploy/state`, process ownership or scheduled tasks | On-PC read-only inventory; reconcile expected vs actual filenames, permissions, task actions and local active release |
| P0 | Full-project restart can misidentify Python children with hidden command lines | Earlier Smart Money PID 36368 had blank Win32_Process.CommandLine and survived script-based cleanup | Fail-closed process identity and permission tests **before stopping healthy traders**; isolated rollback simulation |
| P0 | StockTracker legacy READY_TO_DEPLOY requests contain stale approved blobs | The aggregated StockTrader preflight checked 7 READY requests and blocked 3 historical stale approvals: `P-STOCK-20260929-01`, `P-STOCK-20260929-02`, and `P-STOCK-20261001-01` (v1.9 trader blob differs from approved commit); 4 passed | Compare local `processed_requests.json` and active manifest; quarantine/supersede only after identifying historical deployment state; do not weaken blob checks |
| P1 | Current supervisor OK handshake is not sustained health attestation | Handshake chiefly checks process presence; Smart Money produced DEGRADED output despite a running process | Verify deployed SHA plus repeated runtime health cycles and producer/consumer agreement before claiming release VERIFIED |
| P1 | CI Windows integration is not the user's exact workstation | `windows-latest` has different scheduled tasks, environment, ownership and local state | Add dedicated opt-in dry-run on actual Windows host with a sanitized local result and no restarts |
| P1 | Paper trading engine and StockTracker geo feed lack a universal release health heartbeat | File presence can be stale or validly idle | Add independent service heartbeats and timestamp checks that distinguish market-closed from hung |
| P1 | GitHub branch-protection/ruleset enforcement unverified | A passing/failing Action run alone may not block commits to main | Check repository rules and enable required checks with appropriate repo-admin consent |
| P1 | Local dependency versions / Python interpreter details not yet attested | GitHub runners are not the user's local Python 3.13 install | Read-only capture of interpreter and dependency versions without secrets; pin verified requirements |
| P2 | Historical setup documentation contradicted active runtime | Prior Stock README v1.8 vs fallback v1.9 vs host observation v1.10; old Crypto doc claimed password-based boot task | Reconciled README/startup docs; recheck task installation with host inventory |

## Status vocabulary

- **COMMITTED:** GitHub contains code; nothing implied about Windows.
- **CI_VALIDATED:** Automated tests ran against a specific commit on GitHub runners.
- **HOST_OBSERVED:** A timestamped local inventory identified particular services and evidence.
- **RELEASE_VERIFIED:** Post-deployment code provenance, expected processes and repeated health evidence agreed; not yet implemented end-to-end for every service.
- **BLOCKED:** A fail-closed gate rejected an unsafe/ambiguous release.
- **UNVERIFIED:** Missing evidence; must not be displayed as success.

## Never close by assertion

A green status in a web dashboard, a successful GitHub Action, a running
Windows scheduled task, a single healthy JSON report, and a successful process
spawn each prove **different things**. No one signal establishes full health.

**Guardrail:** LIVE trades are not authorized. Preserve CryptoTracker
`LIVE_TRADING=false`/Helius-disabled settings and StockTracker
`PAPER_ONLY=True` / Alpaca `paper=True`. Do not publish `.env` or local
wallet credentials.
