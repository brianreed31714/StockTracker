"""Publish a strictly sanitized StockTracker host-attestation signal to GitHub.

Writes *only* a single-file status commit on a dedicated branch,
stocktracker-host-status. Uses isolated Git objects/commit-tree; does NOT
change, checkout, stage, commit, rebase, reset, or restart the Windows
trading working tree, and never pushes to main. No GitHub API token required:
uses the existing Git remote credentials. Failure is non-disruptive.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess

STATUS_BRANCH = "refs/heads/stocktracker-host-status"
OUTPUT_FILE = "status.json"
SHA = re.compile(r"^[0-9a-f]{40}$")
DATE = re.compile(r"^20\d{2}-\d\d-\d\d$")
STATES = {
    "UNVERIFIED", "CODE_SYNCED_RUNTIME_UNVERIFIED",
    "CODE_SYNCED_PROCESS_OBSERVED", "HOST_PROCESSES_STABLE_SOURCE_ONLY",
    "EOD_EXECUTION_VERIFIED",
}


def sanitized(report: dict) -> dict:
    if not isinstance(report, dict):
        raise ValueError("Status must be an object")
    state = report.get("state")
    if state not in STATES:
        raise ValueError("Invalid attestation state")
    if (state == "EOD_EXECUTION_VERIFIED") != (report.get("eod_execution_verified") is True):
        raise ValueError("EOD evidence flag disagrees with state")
    if report.get("eod_execution_verified") is True and (
            report.get("processes_stable") is not True or report.get("code_synced") is not True):
        raise ValueError("EOD evidence lacks positive code/process provenance")
    if state == "HOST_PROCESSES_STABLE_SOURCE_ONLY" and report.get("processes_stable") is not True:
        raise ValueError("Stable-process claim lacks evidence")
    head = report.get("git_head")
    if not isinstance(head, str) or not SHA.fullmatch(head):
        # Do not accept missing/partial hashes, even for UNVERIFIED signals.
        raise ValueError("No valid host Git revision")
    value = report.get("observed_at_utc")
    if not isinstance(value, str):
        raise ValueError("Missing timestamp")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("Host timestamp missing timezone")
    # Every output key is explicit; never send process PIDs, logs, machine
    # paths, account data, full exceptions, or messages from the source report.
    payload = {
        "schema": "stocktracker_windows_attestation_v1",
        "project": "StockTracker",
        "observed_at_utc": stamp.astimezone(timezone.utc).isoformat(),
        "git_head": head,
        "state": state,
        "source_code_synced": report.get("code_synced") is True,
        "processes_stable": report.get("processes_stable") is True,
        "post_sync_eod_verified": report.get("eod_execution_verified") is True,
        "in_memory_trader_digest_verified": False,
        "broker_trade_health_verified": False,
    }
    if payload["post_sync_eod_verified"]:
        day = report.get("verified_review_date")
        if not isinstance(day, str) or not DATE.fullmatch(day) or datetime.fromisoformat(day).date().isoformat() != day:
            raise ValueError("Invalid EOD review date")
        payload["verified_review_date"] = day
    return payload


def _git(root: Path, args: list[str], *, data: str | None = None) -> str:
    cmd = ["git", "-C", str(root), *args]
    try:
        res = subprocess.run(cmd, input=data, text=True, capture_output=True, timeout=35)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Git host-status publishing unavailable") from None
    if res.returncode != 0:
        # Exception text can contain remote URLs or authorization diagnostics.
        raise RuntimeError("Git host-status command rejected")
    return res.stdout.strip()


def publish(root: Path, report: dict) -> str:
    """Safe, non-force remote status branch update; no local worktree mutations."""
    root = Path(root).resolve()
    payload = sanitized(report)
    if _git(root, ["branch", "--show-current"]) != "main":
        raise RuntimeError("Host code checkout is not on main")
    refs = _git(root, ["ls-remote", "--heads", "origin", STATUS_BRANCH])
    parent = ""
    if refs:
        parts = refs.splitlines()
        if len(parts) != 1:
            raise RuntimeError("Ambiguous host status branch")
        pair = parts[0].split()
        if len(pair) != 2 or not SHA.fullmatch(pair[0]) or pair[1] != STATUS_BRANCH:
            raise RuntimeError("Invalid remote status ref")
        parent = pair[0]
        _git(root, ["fetch", "--no-tags", "origin", STATUS_BRANCH])
        if _git(root, ["rev-parse", "--verify", "FETCH_HEAD"]) != parent:
            raise RuntimeError("Remote status changed before fetch")
        # Never overwrite other files on a preexisting unrelated status branch.
        content = _git(root, ["ls-tree", "--name-only", "FETCH_HEAD"]).splitlines()
        if content != [OUTPUT_FILE]:
            raise RuntimeError("Existing status branch is not a single-file attestation branch")

    data = json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n"
    blob = _git(root, ["hash-object", "-w", "--stdin"], data=data)
    if not SHA.fullmatch(blob):
        raise RuntimeError("Invalid blob hash")
    tree = _git(root, ["mktree"], data=f"100644 blob {blob}\t{OUTPUT_FILE}\n")
    if not SHA.fullmatch(tree):
        raise RuntimeError("Invalid tree hash")
    args = [
        "-c", "user.name=StockTrackerAttestor",
        "-c", "user.email=stocktracker-attestation@users.noreply.github.com",
        "commit-tree", tree,
    ]
    if parent:
        args += ["-p", parent]
    args += ["-m", f"Host attestation {payload['state']} {payload['git_head'][:10]}"]
    commit = _git(root, args)
    if not SHA.fullmatch(commit):
        raise RuntimeError("Invalid attestation commit")
    # Non-fast-forward updates fail. Never use --force or push to main.
    _git(root, ["push", "origin", f"{commit}:{STATUS_BRANCH}"])
    return commit


if __name__ == "__main__":
    raise SystemExit("Host status publisher is import-only; use activation attestor")
