# Isolated runtime research outputs

This change is **opt-in** and does not alter the trading strategy, Alpaca account configuration, or the current v1.10 process.

Set `STOCKTRACKER_RUNTIME_ROOT` to a directory outside the Git checkout, for example:
`C:\Users\brian\OneDrive\Documents\StockTracker-Runtime`.

The post-close pipeline writes `analysis/daily`, `analysis/evidence`,
`analysis/performance`, `analysis/proposals`, and `post_close_review_state.json`
beneath that directory. The trading database and dashboard remain at their
existing configured paths.

The daily pipeline continues executing locally; when external output is configured,
`sync_proposals_to_git.py` deliberately skips automatic Git commits/pushes.
Reviewed research can be published later through an explicit, separate export,
after scanning for confidential data and reconciling the release branch.

## Migration procedure

1. Keep the Git stash and both recovery ZIPs. Do not use `git stash pop`.
2. Validate the draft CI smoke test.
3. Back up any existing active report state. Copy recovered research folders into
   the external runtime directory **without overwriting newer files**.
4. Enable `STOCKTRACKER_RUNTIME_ROOT` in the machine's local `.env` only
   after files and directories are verified, then run an offline post-close test.
5. Check complete reports and `git status -sb` remains clean. Only then merge
   and activate the change, outside an active trading session.

**Known remaining limitation:** Historically tracked report files under
`analysis/performance` and `analysis/proposals` still exist in Git.
Existing publication scripts or older processes can dirty those files.
The external-output option avoids new writes from the changed scripts, but
does not automatically migrate, delete, or untrack historical artifacts.

Do not run the supervisor or submit a deployment as part of these steps.
