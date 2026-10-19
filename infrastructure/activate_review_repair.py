"""Safely activate the StockTracker paper-only review repair on the Windows host.

No remote execution is possible through GitHub alone. This one-shot LOCAL tool
must be invoked with --apply; default is a read-only preflight. On apply it
terminates ONLY the observed StockTracker paper trader PID and lets the existing
StockTracker supervisor launch its configured replacement. It never restarts
CryptoTracker, the Stock geo feed, dashboard, supervisor, or deployment agent.

The receipt proves only a bounded process restart, never sustained review health.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fnmatch
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import signal
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

from infrastructure.registry_contract import validate_registry, release_preflight
from infrastructure.runtime_inventory import collect, windows_processes, latest_launches, parse_timestamp

ROOT = Path(__file__).resolve().parent.parent
TRADER_NAME = "momentum_trader_v1_10_runtime_audit.py"
REQUIRED_STOCK = ("supervisor", "deployment_agent", "trader", "geo_feed", "dashboard")
REQUIRED_CRYPTO = ("supervisor", "deployment_agent", "trader", "smart_money", "dashboard")
RECEIPT = ROOT / "deploy" / "state" / "review_repair_activation.json"


class ActivationBlocked(RuntimeError):
    pass


def run_readonly(*argv: str, cwd: Path = ROOT, timeout: int = 35) -> str:
    try:
        result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ActivationBlocked("Read-only preflight command unavailable") from exc
    if result.returncode:
        raise ActivationBlocked("Read-only preflight command failed")
    return result.stdout.strip()


def remote_matches_head(root: Path) -> str:
    root = root.resolve()
    if run_readonly("git", "status", "--porcelain", "--untracked-files=all", cwd=root):
        raise ActivationBlocked("Working tree has local changes; refusing activation")
    head = run_readonly("git", "rev-parse", "HEAD", cwd=root)
    remote = run_readonly("git", "rev-parse", "refs/remotes/origin/main", cwd=root)
    branch = run_readonly("git", "branch", "--show-current", cwd=root)
    if head != remote or branch != "main":
        raise ActivationBlocked("Local main does not match origin/main; wait for safe sync")
    return head


def outside_active_hours(now: datetime) -> bool:
    """Weekday protected trading + EOD window: 06:30–13:40 Pacific.

    Use America/Los_Angeles rather than a fixed PDT/PST UTC offset. Weekends
    remain eligible, with all original release, identity and paper checks.
    """
    if now.tzinfo is None:
        raise ActivationBlocked("Time must be timezone-aware")
    pacific = now.astimezone(ZoneInfo("America/Los_Angeles"))
    if pacific.weekday() >= 5:
        return True
    minute_of_day = pacific.hour * 60 + pacific.minute
    return not (6 * 60 + 30 <= minute_of_day < 13 * 60 + 40)


def require_observed_services(snapshot: dict, components: tuple[str, ...]) -> dict[str, int]:
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("components"), dict):
        raise ActivationBlocked("Runtime snapshot unavailable")
    result: dict[str, int] = {}
    for component in components:
        state = snapshot["components"].get(component) or {}
        process = state.get("process") or {}
        version = state.get("script_version") or {}
        pids = process.get("pids") or []
        if process.get("state") != "OBSERVED" or len(pids) != 1:
            raise ActivationBlocked(f"{component}: process identity ambiguous or missing")
        if version.get("state") != "MATCHED":
            raise ActivationBlocked(f"{component}: running script differs from expected release")
        result[component] = int(pids[0])
    return result


def _trader_script_argument(command: str) -> str | None:
    """Inspect the Python executable's actual script argument, not mentions.

    The supervisor launches Python with an absolute script path. An unrelated
    -m / -c Python process may mention the filename elsewhere in its command.
    """
    args = [part.strip('"') for part in re.findall(r'"[^"]*"|\S+', command)]
    if len(args) < 2:
        return None
    executable = PureWindowsPath(args[0]).name.lower()
    if executable not in {"python", "python.exe", "pythonw", "pythonw.exe"}:
        return None
    i = 1
    while i < len(args) and args[i] in {"-u", "-B", "-E", "-s", "-S"}:
        i += 1
    if i >= len(args) or args[i].startswith("-"):
        return None
    return args[i]


def _verified_supervisor_launch(proc: dict, launch: dict | None, script_name: str) -> bool:
    """Correlate a StockTrader supervisor launch with PID and process start.

    Relative script names or hidden command lines have no trustworthy
    repository path and must not be accepted on basename alone.
    """
    if not launch or PureWindowsPath(str(launch.get("script") or "")).name.lower() != script_name.lower():
        return False
    if str(launch.get("label") or "").strip().lower() != "trader":
        return False
    try:
        launched_utc = datetime.fromisoformat(str(launch["time"])).astimezone(timezone.utc)
        started_utc = parse_timestamp(str(proc.get("started_utc") or ""))
    except (TypeError, ValueError, OverflowError):
        return False
    return abs((started_utc - launched_utc).total_seconds()) <= 90


def relative_process_cwd_evidence(proc: dict, root: Path) -> str:
    """Independent read-only evidence for an executing *relative* script.

    psutil reads the OS-owned current directory and creation time of the PID.
    A bare script name is never enough: accept it only if the actual process
    has the StockTracker working directory AND the Windows CIM start timestamp
    agrees with the OS process start time. All failure cases fail closed.
    No paths, argv, or credentials are logged.
    """
    pid = int(proc.get("pid") or 0)
    if pid <= 0:
        return "INVALID_PID"
    try:
        started = parse_timestamp(str(proc.get("started_utc") or ""))
    except (ValueError, TypeError, OverflowError):
        return "UNVERIFIED_START_TIME"
    try:
        import psutil
    except ImportError:
        return "PSUTIL_NOT_INSTALLED"
    try:
        process = psutil.Process(pid)
        with process.oneshot():
            created = float(process.create_time())
            actual_directory = process.cwd()
    except (psutil.NoSuchProcess, psutil.ZombieProcess):
        return "PROCESS_EXITED"
    except (psutil.AccessDenied, OSError, ValueError):
        return "CWD_ACCESS_UNAVAILABLE"

    # Windows CIM and psutil use different clocks/precisions, and process
    # startup may be rounded; a generous 3s tolerance is still far tighter
    # than a typical PID reuse interval. Check again immediately before stop.
    if abs(started.timestamp() - created) > 3:
        return "PID_CREATION_TIME_MISMATCH"
    try:
        expected = os.path.normcase(str(root.resolve()))
        observed = os.path.normcase(str(Path(actual_directory).resolve()))
    except (OSError, ValueError, TypeError):
        return "CWD_ACCESS_UNAVAILABLE"
    if expected != observed:
        return "FOREIGN_WORKING_DIRECTORY"
    return "MATCHED"


def matching_traders(processes: list[dict], root: Path, name: str = TRADER_NAME,
                     *, launches: dict[int, dict] | None = None) -> list[dict]:
    """Require exact script path or independently attested supervisor spawn."""
    root = root.resolve()
    if launches is None:
        launches = latest_launches(root / "deploy" / "state" / "supervisor.log")
    expected = str(root / name).replace("\\", "/").casefold()
    matches = []
    for proc in processes:
        pid = int(proc.get("pid") or 0)
        if pid <= 0:
            continue
        script = _trader_script_argument(str(proc.get("command") or ""))
        if script:
            if PureWindowsPath(script).name.casefold() != name.casefold():
                continue
            normalized = script.replace("\\", "/").casefold()
            if normalized == expected:
                matches.append({**proc, "provenance": "exact_executable_script_path"})
                continue
            if PureWindowsPath(script).is_absolute() or Path(script).is_absolute():
                raise ActivationBlocked(
                    "Another Python process executes the same trader script outside StockTracker"
                )
        if (
            (not script or PureWindowsPath(script).name.casefold() == name.casefold())
            and _verified_supervisor_launch(proc, launches.get(pid), name)
        ):
            matches.append({**proc, "provenance": "supervisor_pid_start_time"})
            continue
        # The live Oct 19 Windows trader uses an actual relative script path
        # but has no matching supervisor launch record. Verify its *OS-owned*
        # working directory and creation time; no filename-only fallback.
        if (
            script
            and PureWindowsPath(script).name.casefold() == name.casefold()
            and not PureWindowsPath(script).is_absolute()
            and not Path(script).is_absolute()
            and relative_process_cwd_evidence(proc, root) == "MATCHED"
        ):
            matches.append({**proc, "provenance": "process_cwd_and_start_time"})
    return matches



def validate_target(snapshot: dict, processes: list[dict], root: Path) -> dict:
    stock = require_observed_services(snapshot, REQUIRED_STOCK)
    current = matching_traders(processes, root)
    if len(current) != 1 or current[0].get("pid") != stock["trader"]:
        # Explain which independent ownership proof is missing without
        # printing raw command lines, directory names or credentials.
        if not current:
            inventory_pid = stock["trader"]
            observed = next(
                (p for p in processes if int(p.get("pid") or 0) == inventory_pid),
                None,
            )
            if observed is not None:
                script = _trader_script_argument(str(observed.get("command") or ""))
                if script and PureWindowsPath(script).name.casefold() == TRADER_NAME.casefold():
                    if not PureWindowsPath(script).is_absolute() and not Path(script).is_absolute():
                        reason = relative_process_cwd_evidence(observed, root)
                        raise ActivationBlocked(
                            "Relative trader process ownership not verified: " + reason
                        )
        raise ActivationBlocked("Refusing to target an ambiguous trader process")
    active_files = snapshot.get("active_manifest_files") or {}
    if active_files.get("trader") != TRADER_NAME:
        raise ActivationBlocked("Active manifest does not select approved v1.10 trader")
    selected = snapshot["components"]["trader"]["script_version"]
    if selected.get("observed_script", "").lower() != TRADER_NAME.lower():
        raise ActivationBlocked("Observed trader version is not the reviewed v1.10 script")
    return current[0]


def assert_review_idle(snapshot: dict, root: Path):
    for task in snapshot.get("tasks") or []:
        if task.get("name") == "StockTracker Daily Review" and str(task.get("state")).lower() == "running":
            raise ActivationBlocked("Daily Review scheduled task is running")
    state = root / "post_close_review_state.json"
    if state.is_file():
        try:
            data = json.loads(state.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise ActivationBlocked("Review state cannot be safely inspected")
        if data.get("status") == "RUNNING":
            # Do not interrupt a running review, even if the lock has been
            # left stale; resolve the stale state separately.
            raise ActivationBlocked("Review state reports RUNNING; do not interrupt")


def assert_paper_safe(root: Path):
    registry = validate_registry(root, check_local_safety=True)
    release_preflight(root, ["trader"], {"trader": TRADER_NAME})
    trader_source = (root / TRADER_NAME).read_text(encoding="utf-8")
    if "PAPER_ONLY = True" not in trader_source or "paper=True" not in trader_source:
        raise ActivationBlocked("Broker execution is not confirmed PAPER ONLY")
    if "from post_close_review_policy import review_retry_decision" not in trader_source:
        raise ActivationBlocked("Updated trader review policy has not synced")
    if not (root / "post_close_review_guard.py").is_file():
        raise ActivationBlocked("Updated shared review guard missing")
    return registry


def record_receipt(data: dict):
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    temp = RECEIPT.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(RECEIPT)


def inspect_host(root: Path) -> tuple[dict, dict, dict, dict, str]:
    if os.name != "nt":
        raise ActivationBlocked("Activation requires the actual Windows host")
    if not outside_active_hours(datetime.now(timezone.utc)):
        raise ActivationBlocked("Market/review blackout 06:30–13:40 Pacific weekdays")
    head = remote_matches_head(root)
    assert_paper_safe(root)
    stock = collect(root)
    crypto_root = root.parent / "CryptoTracker"
    if not crypto_root.is_dir():
        raise ActivationBlocked("Sibling CryptoTracker path unavailable for isolation baseline")
    crypto = collect(crypto_root)
    require_observed_services(crypto, REQUIRED_CRYPTO)
    assert_review_idle(stock, root)
    procs = windows_processes()
    target = validate_target(stock, procs, root)
    return stock, crypto, target, dict(target), head


def confirm_unchanged(old: dict, new: dict, ids: tuple[str, ...]) -> list[str]:
    a = require_observed_services(old, ids)
    b = require_observed_services(new, ids)
    return [cid for cid in ids if a[cid] != b[cid]]


def activate(root: Path = ROOT, *, apply: bool = False, timeout_seconds: int = 200,
             stable_seconds: int = 65) -> dict:
    root = root.resolve()
    global RECEIPT
    RECEIPT = root / "deploy" / "state" / "review_repair_activation.json"
    stock, crypto, target, _, head = inspect_host(root)
    old_pid = int(target["pid"])
    result = {
        "status": "VALIDATED_NO_CHANGE",
        "paper_only": True,
        "project": "StockTracker",
        "code_head": head,
        "prior_manifest_commit": stock.get("active_manifest_commit"),
        "prior_trader_pid": old_pid,
        "other_projects_modified": False,
        "release_verified": False,
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    if not apply:
        return result

    # Tests load only the isolated review guard and AST of the trader; they do
    # not construct Alpaca TradingClient or place paper/live orders.
    run_readonly(
        sys.executable, "-m", "unittest", "-q", "test_review_retry_safety.RetryPolicyTests",
        "test_review_retry_safety.GuardTests",
        "test_review_retry_safety.BatchRunnerContractTests",
        "infrastructure.test_eod_timing", "infrastructure.test_pacific_times",
        cwd=root, timeout=100,
    )
    if not outside_active_hours(datetime.now(timezone.utc)):
        raise ActivationBlocked("Entered trading/review blackout during preflight")
    if remote_matches_head(root) != head:
        raise ActivationBlocked("Git HEAD changed during preflight")

    # Re-read immediately before termination; prevent stale PID or
    # already-restarted-process targeting. Never kill the supervisor.
    before = collect(root)
    if require_observed_services(before, REQUIRED_STOCK)["trader"] != old_pid:
        raise ActivationBlocked("Trader PID changed during preflight")
    latest = validate_target(before, windows_processes(), root)
    if latest.get("started_utc") != target.get("started_utc"):
        raise ActivationBlocked("Trader PID was reused since preflight")
    result["status"] = "TRADER_RESTART_REQUESTED"
    record_receipt(result)

    # Stop ONE positively identified paper-only trader. The existing
    # supervisor restarts it; we DO NOT launch a competing second trader.
    stop = subprocess.run(["taskkill", "/PID", str(old_pid), "/F"],
                          capture_output=True, text=True, timeout=25, cwd=root)
    if stop.returncode:
        result["status"] = "STOP_FAILED"
        record_receipt(result)
        raise ActivationBlocked("Trader PID could not be stopped; no additional process targeted")

    deadline = time.monotonic() + timeout_seconds
    replacement_pid = None
    replacement_seen_at = None
    while time.monotonic() < deadline:
        time.sleep(5)
        observed = windows_processes()
        traders = matching_traders(observed, root)
        if len(traders) > 1:
            result["status"] = "UNSAFE_DUPLICATE_TRADERS"
            record_receipt(result)
            raise ActivationBlocked("Multiple matching traders detected; no other process will be killed")
        if len(traders) == 1 and int(traders[0]["pid"]) != old_pid:
            replacement_pid = int(traders[0]["pid"])
            replacement_seen_at = time.monotonic()
            break

    if replacement_pid is None:
        result["status"] = "RESTART_NOT_OBSERVED"
        record_receipt(result)
        raise ActivationBlocked("Supervisor did not restore trader within timeout; do not claim success")

    while time.monotonic() - replacement_seen_at < stable_seconds:
        time.sleep(5)
        traders = matching_traders(windows_processes(), root)
        if len(traders) != 1 or int(traders[0]["pid"]) != replacement_pid:
            result["status"] = "REPLACEMENT_UNSTABLE"
            record_receipt(result)
            raise ActivationBlocked("Trader PID changed or duplicated during stability window")

    after = collect(root)
    after_crypto = collect(root.parent / "CryptoTracker")
    stock_changed = confirm_unchanged(
        before, after, ("supervisor", "deployment_agent", "geo_feed", "dashboard")
    )
    crypto_changed = confirm_unchanged(crypto, after_crypto, REQUIRED_CRYPTO)
    result.update({
        "new_trader_pid": replacement_pid,
        "other_stock_component_pids_changed": stock_changed,
        "crypto_component_pids_changed": crypto_changed,
        "other_projects_modified": False,
        "post_trader_script_state": after["components"]["trader"]["script_version"]["state"],
    })
    if (
        after["components"]["trader"]["process"]["pids"] != [replacement_pid]
        or result["post_trader_script_state"] != "MATCHED"
        or stock_changed or crypto_changed
    ):
        result["status"] = "ACTIVATED_WITH_UNRESOLVED_RUNTIME_DISCREPANCY"
    else:
        result["status"] = "PAPER_TRADER_RESTART_OBSERVED"
    # Deliberately no 'release_verified=True': the next genuine market-close
    # review, reporting artifact, and scheduled task health still need proof.
    record_receipt(result)
    return result


def main():
    ap = argparse.ArgumentParser(description="Stock-only paper EOD review repair activation")
    ap.add_argument("--apply", action="store_true",
                    help="After safety checks, stop ONLY the current paper trader and let supervisor restore it")
    args = ap.parse_args()
    try:
        result = activate(apply=args.apply)
        print(json.dumps(result, sort_keys=True, indent=2))
    except ActivationBlocked as exc:
        print("BLOCKED: " + str(exc), file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
