"""StockTracker Windows activation attestation (non-destructive, fail closed).

Called by the *already authorized* StockTracker deployment-agent loop after
its successful fast-forward sync. This never starts/stops a process, submits a
trade, modifies scheduled tasks, exposes a command line, or publishes raw logs.

Important distinction:
  CODE_SYNCED: Git source files are on Windows, not proof of an in-memory reload.
  PROCESSES_STABLE: three separated host observations of expected script IDs.
  EOD_EXECUTION_VERIFIED: a newly executed post-sync local review completed and
      wrote matching, fresh artifacts. This is not broker correctness or reboot
      recovery proof.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from infrastructure.runtime_inventory import collect, git_head, parse_timestamp

REPORT_NAME = "activation_attestation.json"
REQUIRED_PROCESSES = ("supervisor", "deployment_agent", "trader", "geo_feed", "dashboard")
REQUIRED_SCRIPT_VERSIONS = ("trader", "geo_feed", "dashboard")
MIN_SECONDS_BETWEEN_SAMPLES = 20
REQUIRED_SAMPLES = 3
SHA = re.compile(r"^[0-9a-f]{40}$")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, TypeError, ValueError):
        return {}


def _head(root: Path, rev: str) -> str:
    try:
        response = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", rev],
            text=True, capture_output=True, timeout=10,
        )
        value = response.stdout.strip().lower()
        return value if response.returncode == 0 and SHA.fullmatch(value) else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _code_clean(root: Path) -> bool:
    """Only compare source files; mutable external reports must stay irrelevant."""
    try:
        res = subprocess.run(
            ["git", "-C", str(root), "diff", "--quiet", "--",
             "infrastructure", "stocktracker_deployment_agent.py",
             "stocktracker_supervisor.py", "run_daily_model_review.bat",
             "sync_proposals_to_git.py", "safe_summary_publish.py",
             "daily_model_review.py", "proposal_registry.py",
             "publish_supporting_evidence.py", "build_daily_review_bundle.py"],
            timeout=10, capture_output=True,
        )
        staged = subprocess.run(
            ["git", "-C", str(root), "diff", "--cached", "--quiet", "--",
             "infrastructure", "stocktracker_deployment_agent.py",
             "stocktracker_supervisor.py", "run_daily_model_review.bat",
             "sync_proposals_to_git.py", "safe_summary_publish.py",
             "daily_model_review.py", "proposal_registry.py",
             "publish_supporting_evidence.py", "build_daily_review_bundle.py"],
            timeout=10, capture_output=True,
        )
        return res.returncode == staged.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _external_runtime(root: Path) -> Path:
    setting = os.getenv("STOCKTRACKER_RUNTIME_ROOT", "").strip()
    if not setting:
        return root
    runtime = Path(setting).expanduser().resolve()
    if runtime == root or root in runtime.parents:
        raise ValueError("Invalid isolated runtime root")
    return runtime


def review_after_sync(root: Path, first_seen: str, *, clock: datetime | None = None) -> dict:
    """Prove *this* code-sync preceded a completed dated EOD cycle."""
    runtime = _external_runtime(root)
    state = _read_json(runtime / "post_close_review_state.json")
    if not state and runtime != root:
        # Never silently accept a stale legacy file when external storage is on.
        return {"state": "NOT_VERIFIED", "reason": "REVIEW_STATE_MISSING"}
    day = str(state.get("review_date") or "")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) or state.get("status") != "COMPLETED":
        return {"state": "NOT_VERIFIED", "reason": "REVIEW_NOT_COMPLETED"}
    try:
        finished = parse_timestamp(str(state.get("finished_at") or ""))
        start = parse_timestamp(first_seen)
        now = clock or now_utc()
        if finished < start or finished > now:
            return {"state": "NOT_VERIFIED", "reason": "REVIEW_OUTSIDE_SYNC_WINDOW"}
    except (ValueError, TypeError):
        return {"state": "NOT_VERIFIED", "reason": "MISSING_REVIEW_FINISH_TIMESTAMP"}
    perf = _read_json(runtime / "analysis" / "performance" / "latest.json")
    manifest = _read_json(runtime / "analysis" / "evidence" / day / "manifest.json")
    metrics = perf.get("metrics") or {}
    review = perf.get("review") or {}
    integrity = manifest.get("integrity_analysis") or {}
    if (metrics.get("review_date") != day or review.get("review_date") != day
            or metrics.get("paper_only") is not True or
            manifest.get("review_date") != day or
            manifest.get("paper_only") is not True or
            manifest.get("sanitized") is not True or
            manifest.get("source_database_present") is not True or
            integrity.get("status") != "PASS"):
        return {"state": "NOT_VERIFIED", "reason": "REPORT_ARTIFACT_DATE_OR_INTEGRITY_MISSING"}
    # Merely producing a new COMPLETED flag cannot retroactively validate an
    # older report, even one from the same day.
    try:
        for generated_at in (metrics.get("generated_at"), review.get("generated_at"),
                             manifest.get("generated_at")):
            when = parse_timestamp(str(generated_at or ""))
            if not start <= when <= finished:
                return {"state": "NOT_VERIFIED", "reason": "ARTIFACT_NOT_FROM_POST_SYNC_REVIEW"}
    except (ValueError, TypeError):
        return {"state": "NOT_VERIFIED", "reason": "ARTIFACT_TIMESTAMP_UNVERIFIED"}
    return {"state": "VERIFIED", "review_date": day}


def evaluate_snapshot(snapshot: dict) -> tuple[bool, dict, list[str]]:
    components = snapshot.get("components") or {}
    reasons = []
    # Process and script-version checks must ALL be positively observed.
    evidence = {}
    for name in REQUIRED_PROCESSES:
        component = components.get(name) or {}
        proc = component.get("process") or {}
        version = component.get("script_version") or {}
        pids = proc.get("pids") or []
        if proc.get("state") != "OBSERVED" or len(pids) != 1 or not isinstance(pids[0], int):
            reasons.append("PROCESS_UNVERIFIED_" + name.upper())
            continue
        # Include observed Windows creation time to reject PID reuse across polls.
        started = proc.get("started_utc")
        try:
            if not started:
                raise ValueError("missing start provenance")
            parse_timestamp(started)
        except (ValueError, TypeError):
            reasons.append("START_TIME_UNVERIFIED_" + name.upper())
            continue
        if name in REQUIRED_SCRIPT_VERSIONS and version.get("state") != "MATCHED":
            reasons.append("SCRIPT_VERSION_UNVERIFIED_" + name.upper())
            continue
        evidence[name] = (pids[0], started, str(proc.get("script") or ""))
    return not reasons, evidence, reasons


def advance(root: Path, previous: dict, snapshot: dict, *,
            head: str, upstream: str, clean: bool, clock: datetime) -> dict:
    """Pure state machine; never equate synchronized source with executing code."""
    timestamp = clock.isoformat()
    result = {
        "schema_version": 1,
        "observed_at_utc": timestamp,
        "git_head": head if SHA.fullmatch(head or "") else "UNVERIFIED",
        "origin_main": upstream if SHA.fullmatch(upstream or "") else "UNVERIFIED",
        "state": "UNVERIFIED",
        "code_synced": False,
        "processes_stable": False,
        "eod_execution_verified": False,
        "consecutive_observations": 0,
        "first_seen_at_utc": timestamp,
        "last_sample_at_utc": timestamp,
        "fingerprint": {},
        "reasons": [],
        "notice_key": str(previous.get("notice_key") or ""),
        "notification": "UNCONFIRMED",
    }
    if not head or head != upstream or not SHA.fullmatch(head) or not clean:
        result["reasons"] = ["GIT_SYNC_OR_SOURCE_INTEGRITY_UNVERIFIED"]
        return result
    result["code_synced"] = True
    same_head = previous.get("git_head") == head and previous.get("code_synced") is True
    if same_head:
        result["first_seen_at_utc"] = previous.get("first_seen_at_utc", timestamp)
    passed, evidence, reasons = evaluate_snapshot(snapshot)
    if not passed:
        result["state"] = "CODE_SYNCED_RUNTIME_UNVERIFIED"
        result["reasons"] = reasons
        return result
    result["state"] = "CODE_SYNCED_PROCESS_OBSERVED"
    fingerprint = {name: list(details) for name, details in sorted(evidence.items())}
    result["fingerprint"] = fingerprint
    prior_fingerprint = previous.get("fingerprint") or {}
    previous_stamp = previous.get("last_sample_at_utc") or ""
    try:
        interval = (clock - parse_timestamp(previous_stamp)).total_seconds()
    except (ValueError, TypeError):
        interval = -1
    if same_head and prior_fingerprint == fingerprint and interval >= MIN_SECONDS_BETWEEN_SAMPLES:
        result["consecutive_observations"] = min(
            REQUIRED_SAMPLES, max(0, int(previous.get("consecutive_observations") or 0)) + 1
        )
    else:
        result["consecutive_observations"] = 1
    if result["consecutive_observations"] < REQUIRED_SAMPLES:
        return result
    result["processes_stable"] = True
    result["state"] = "HOST_PROCESSES_STABLE_SOURCE_ONLY"
    status = review_after_sync(root, result["first_seen_at_utc"], clock=clock)
    if status.get("state") == "VERIFIED":
        result["state"] = "EOD_EXECUTION_VERIFIED"
        result["eod_execution_verified"] = True
        result["verified_review_date"] = status["review_date"]
    else:
        result["reasons"] = [str(status.get("reason") or "REVIEW_NOT_VERIFIED")]
    # Trading correctness / in-memory source digest / reboot recovery NOT proven.
    return result


def atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    candidate = path.with_suffix(".tmp")
    candidate.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    candidate.replace(path)


def poll(root: Path, *, observation: dict | None = None,
         clock: datetime | None = None, expected_sha: str = "",
         notify: Callable[[str, str], bool] | None = None,
         remote_publish: Callable[[Path, dict], str] | None = None) -> dict:
    """One bounded observation by a Windows-hosted, already running agent.

    Optional notification is supplied by agent's Pushover sender; an unverified
    or missing process never sends a 'verified deployment' message.
    """
    if os.name != "nt" and observation is None:
        raise RuntimeError("Windows-only host collection")
    root = Path(root).resolve()
    state_path = root / "deploy" / "state" / REPORT_NAME
    previous = _read_json(state_path)
    stamp = clock or now_utc()
    head = git_head(root)
    origin = _head(root, "refs/remotes/origin/main")
    if expected_sha and (not SHA.fullmatch(expected_sha) or expected_sha != head):
        origin = ""  # Explicit pinned commit does not match.
    clean = _code_clean(root)
    # Never use a GitHub CI snapshot as a substitute for this Windows read.
    try:
        snapshot = observation if observation is not None else collect(root)
        report = advance(root, previous, snapshot, head=head,
                         upstream=origin, clean=clean, clock=stamp)
    except (ValueError, TypeError, OSError, RuntimeError):
        report = advance(root, previous, {}, head="", upstream="", clean=False, clock=stamp)
        report["reasons"] = ["HOST_INVENTORY_UNAVAILABLE"]
    # Every distinct commit gets a CODE_SYNCED notice after positive source
    # integrity; a later EOD verification gets a second distinct notice.
    # Do not send repeated notices for each 60-second polling interval.
    if report["code_synced"]:
        target = "EOD_VERIFIED" if report["eod_execution_verified"] else "SOURCE_SYNCED"
        key = report["git_head"] + ":" + target
        if key == previous.get("notice_key"):
            report["notice_key"] = key
            report["notification"] = previous.get("notification", "UNCONFIRMED")
        elif notify is not None:
            title = ("StockTracker Windows EOD Verified" if report["eod_execution_verified"]
                     else "StockTracker Windows Code Synced")
            body = (f"{report['git_head'][:10]} | {report['state']}. "
                    "Source sync is not proof of a reloaded trader."
                    if target == "SOURCE_SYNCED" else
                    f"{report['git_head'][:10]} | EOD execution and report artifacts verified "
                    f"for {report['verified_review_date']}. Broker/trading health not attested.")
            try:
                delivered = notify(title, body) is True
            except Exception:
                delivered = False
            # Failed Pushover attempts remain eligible for one later retry.
            if delivered:
                report["notice_key"] = key
                report["notification"] = "API_ACCEPTED"
    # Dedicated non-main Git branch makes this proof independently readable
    # in GitHub/ChatGPT, without committing into the trading checkout. Never
    # publish process IDs, account data or raw receipt contents.
    remote_key = (report["git_head"] + ":" + report["state"] + ":" +
                  str(report.get("verified_review_date") or ""))
    if remote_publish is None and os.name == "nt" and observation is None:
        from infrastructure.host_status_publisher import publish as remote_publish
    enabled = os.getenv("STOCKTRACKER_ATTESTATION_REMOTE_ENABLED", "1").strip().lower() not in (
        "0", "false", "no", "off")
    if report["code_synced"] and remote_publish is not None and enabled:
        if remote_key == previous.get("remote_key"):
            report["remote_key"] = remote_key
            report["remote_publish"] = "PUBLISHED"
        else:
            try:
                remote_publish(root, report)
                report["remote_key"] = remote_key
                report["remote_publish"] = "PUBLISHED"
            except Exception:
                # Git credentials, branch protection or concurrency may reject
                # the update; this must never interrupt the trader or EOD.
                report["remote_key"] = str(previous.get("remote_key") or "")
                report["remote_publish"] = "UNCONFIRMED"
    else:
        report["remote_key"] = str(previous.get("remote_key") or "")
        report["remote_publish"] = "DISABLED" if not enabled else "UNCONFIRMED"
    atomic_write(state_path, report)
    return report

def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="One-shot, read-only Windows activation evidence")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--expect", default="", help="Optional exact 40-character expected Git HEAD")
    parser.add_argument("--notify", action="store_true", help="Send Pushover if host-configured and state changed")
    args = parser.parse_args()
    try:
        if os.name != "nt":
            raise RuntimeError("Windows required for host attestation")
        notifier = None
        if args.notify:
            from stocktracker_deployment_agent import push_attestation
            notifier = push_attestation
        receipt = poll(args.root, expected_sha=args.expect, notify=notifier)
        # Output intentionally excludes PIDs, task history, user paths, logs and secrets.
        print(json.dumps({
            "state": receipt["state"],
            "git_head": receipt["git_head"],
            "processes_stable": receipt["processes_stable"],
            "eod_execution_verified": receipt["eod_execution_verified"],
            "notification": receipt["notification"],
            "remote_publish": receipt["remote_publish"],
        }, sort_keys=True))
        return 0 if receipt["code_synced"] else 2
    except (OSError, RuntimeError, ValueError):
        print('{"state": "UNVERIFIED", "reason": "HOST_ATTESTATION_UNAVAILABLE"}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
