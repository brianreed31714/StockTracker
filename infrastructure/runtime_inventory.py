"""Read-only Windows runtime evidence collector for one repo.

No process stops/starts, no trades, no network, no environment dump,
and no secret values or raw process command lines in output. Reports stay
inside gitignored deploy/state; GitHub commit != host verification.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fnmatch
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

from infrastructure.registry_contract import validate_registry, components_by_id, config_values, safe_path


LOG_RE = re.compile(
    r"^(?P<time>\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d) \| Started "
    r"(?P<label>[^:]+): (?P<script>[\w./-]+\.py) pid=(?P<pid>\d+)$"
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_timestamp(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("timestamp without timezone")
    return dt.astimezone(timezone.utc)


def powershell_json(program: str):
    if os.name != "nt":
        raise RuntimeError("Host discovery is Windows-only; use fixture tests in CI")
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", program],
        text=True, capture_output=True, timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode != 0:
        raise RuntimeError("Read-only Windows process/task query failed")
    return json.loads(result.stdout or "null")


def windows_processes() -> list[dict]:
    query = r"""
$rows = @(
  Get-CimInstance Win32_Process |
  Where-Object { $_.Name -match '^python(w)?(\.exe)?$' } |
  ForEach-Object {
    [pscustomobject]@{
      pid = [int]$_.ProcessId
      name = [string]$_.Name
      command = [string]$_.CommandLine
      started_utc = if ($_.CreationDate) { $_.CreationDate.ToUniversalTime().ToString('o') } else { '' }
    }
  }
)
ConvertTo-Json -InputObject $rows -Depth 4 -Compress
"""
    return powershell_json(query) or []


def windows_tasks(names: list[str]) -> list[dict]:
    # All names come from validated registry values, never from an incoming request.
    literal_names = ",".join("'" + name.replace("'", "''") + "'" for name in names)
    query = r"""
$rows = @()
foreach ($name in @(""" + literal_names + r""")) {
  $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
  if ($null -eq $task) {
    $rows += [pscustomobject]@{name=$name; state='MISSING'; last_result=$null; run_level=''; action_script=''}
    continue
  }
  $info = Get-ScheduledTaskInfo -TaskName $name -ErrorAction SilentlyContinue
  $action = @($task.Actions) | Select-Object -First 1
  $args = [string]$action.Arguments
  # No raw task arguments, execution paths, or user IDs leave the probe.
  $script = if ($args -match '([\w.-]+\.(?:py|bat))') { $Matches[1] } else { '' }
  $rows += [pscustomobject]@{
    name=$name
    state=[string]$task.State
    last_result=if ($info) { [int64]$info.LastTaskResult } else { $null }
    run_level=[string]$task.Principal.RunLevel
    action_script=$script
  }
}
ConvertTo-Json -InputObject $rows -Depth 4 -Compress
"""
    return powershell_json(query) or []


def latest_launches(log_file: Path) -> dict[int, dict]:
    records = {}
    if not log_file.is_file():
        return records
    for line in log_file.read_text(encoding="utf-8", errors="replace").splitlines()[-2000:]:
        match = LOG_RE.match(line.strip())
        if not match:
            continue
        fields = match.groupdict()
        records[int(fields["pid"])] = fields
    return records


def associate_process(component: dict, processes: list[dict], launches: dict[int, dict],
                      *, max_launch_skew_seconds: int = 90) -> dict:
    """Only trust hidden-command PIDs with matching supervisor log + start time."""
    pattern = component.get("script_pattern")
    if not pattern or component.get("role") in {"library", "scheduled_job"}:
        return {"state": "NOT_PROCESS", "pids": [], "identification": "not_applicable"}

    matching = []
    for proc in processes:
        pid = int(proc.get("pid") or 0)
        command = str(proc.get("command") or "")
        started = str(proc.get("started_utc") or "")
        direct = False
        # Match whole script basename tokens; do not match an adjacent backup name.
        if command:
            names = re.findall(r"(?i)(?<![\w.])([\w.-]+\.py)(?![\w.])", command)
            direct = any(fnmatch.fnmatch(name.lower(), pattern.lower()) for name in names)
        inferred = False
        if not command and pid in launches and started:
            launch = launches[pid]
            expected = PurePosixPath(launch["script"]).name
            if fnmatch.fnmatch(expected.lower(), pattern.lower()):
                try:
                    # Supervisor.log contains local system time without a timezone.
                    # Runtime probe runs on that same host, so local tz is correct.
                    log_time = datetime.fromisoformat(launch["time"]).astimezone(timezone.utc)
                    started_dt = parse_timestamp(started)
                    inferred = abs((started_dt - log_time).total_seconds()) <= max_launch_skew_seconds
                except (ValueError, OverflowError):
                    inferred = False
        if direct or inferred:
            matching.append({"pid": pid, "identified_by": "command_line" if direct else "supervisor_log_verified_start"})
    if len(matching) > 1:
        return {"state": "DUPLICATE", "pids": [p["pid"] for p in matching], "identification": "multiple"}
    if matching:
        return {"state": "OBSERVED", "pids": [matching[0]["pid"]],
                "identification": matching[0]["identified_by"]}
    return {"state": "UNKNOWN", "pids": [],
            "identification": "not_visible_or_missing"}


def report_health(root: Path, component: dict, *, now: datetime | None = None) -> dict:
    health = component.get("health") or {}
    artifact = health.get("artifact")
    if not artifact:
        return {"state": "NO_ARTIFACT_CONTRACT"}
    p = safe_path(root, artifact)
    if p.is_dir():
        return {"state": "OBSERVED_DIRECTORY"}
    if not p.is_file():
        return {"state": "MISSING"}
    if health.get("type") != "json_heartbeat":
        age = max(0, ((now or utc_now()).timestamp() - p.stat().st_mtime))
        return {"state": "OBSERVED_FILE", "age_seconds": int(age)}
    try:
        report = json.loads(p.read_text(encoding="utf-8"))
        observed = parse_timestamp(report["observed_at_utc"])
        age = ((now or utc_now()) - observed).total_seconds()
        tracked = int(report["tracked_wallets"])
        success = int(report["successful_wallet_checks"])
        failed = int(report["failed_wallet_checks"])
        status = str(report["status"]).upper()
        if tracked <= 0 or success < 0 or failed < 0 or success + failed != tracked:
            raise ValueError("inconsistent wallet counts")
        result = {"age_seconds": int(max(0, age)), "wallets_successful": success,
                  "wallets_total": tracked, "cycle": int(report["cycle_number"])}
        if age < -60:
            result["state"] = "CLOCK_SKEW"
        elif age > int(health["max_age_seconds"]):
            result["state"] = "STALE"
        elif status == "OK" and success == tracked and failed == 0:
            result["state"] = "HEALTHY"
        elif status == "DEGRADED" and failed > 0 and success > 0:
            result["state"] = "DEGRADED"
        elif status == "ERROR" and success == 0 and failed > 0:
            result["state"] = "ERROR"
        else:
            result["state"] = "INCONSISTENT"
        return result
    except (OSError, TypeError, ValueError, KeyError, OverflowError):
        return {"state": "UNREADABLE"}


def git_head(root: Path) -> str:
    try:
        result = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                                text=True, capture_output=True, timeout=12)
        if result.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}\n?", result.stdout):
            return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "UNKNOWN"


def collect(root: Path) -> dict:
    root = Path(root).resolve()
    registry = validate_registry(root, check_local_safety=True)
    if os.name != "nt":
        raise RuntimeError("Actual host observations are available on Windows only")
    task_names = [t["name"] for t in registry["scheduled_tasks"]]
    try:
        tasks = windows_tasks(task_names)
        processes = windows_processes()
        discovery_error = None
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired):
        tasks, processes = [], []
        discovery_error = "Host process/task read-only discovery unavailable"
    try:
        manifest = json.loads((root / registry["runtime_manifest"]).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        manifest = {}
    if not isinstance(manifest, dict):
        manifest = {}
    launchlog = latest_launches(root / "deploy" / "state" / "supervisor.log")
    observed = {}
    for component in registry["components"]:
        cid = component["id"]
        observed[cid] = {
            "process": associate_process(component, processes, launchlog),
            "artifact": report_health(root, component),
        }
    warnings = []
    for task in tasks:
        expected = next(t["script"] for t in registry["scheduled_tasks"] if t["name"] == task["name"])
        state = task.get("state")
        expected_running = task["name"].endswith(" Supervisor")
        if state not in ({"Running"} if expected_running else {"Running", "Ready"}):
            warnings.append(f"Scheduled task not in expected state: {task['name']}")
        if task.get("run_level", "").lower() != "highest":
            warnings.append(f"Scheduled task is not configured for Highest run level: {task['name']}")
        if task.get("action_script") and task["action_script"] != Path(expected).name:
            warnings.append(f"Unexpected scheduled task script: {task['name']}")
    if discovery_error:
        warnings.append(discovery_error)
    for cid, state in observed.items():
        if state["process"]["state"] == "DUPLICATE":
            warnings.append(f"Duplicate process: {cid}")
        if state["process"]["state"] == "UNKNOWN" and registry["components"]:
            warnings.append(f"Process identity unverified: {cid}")
        if state["artifact"]["state"] in {"MISSING", "STALE", "DEGRADED", "ERROR", "INCONSISTENT", "UNREADABLE", "CLOCK_SKEW"}:
            warnings.append(f"Artifact health needs attention: {cid}")
    active_files = {}
    for component, path in (manifest.get("files") or {}).items():
        if isinstance(component, str) and isinstance(path, str):
            active_files[component] = PurePosixPath(path.replace("\\", "/")).name
    return {
        "schema_version": 1, "project": registry["project"], "observed_at_utc": utc_now().isoformat(),
        "git_head": git_head(root),
        "active_manifest_commit": str(manifest.get("commit") or "UNVERIFIED"),
        "active_manifest_files": active_files,
        "tasks": tasks,
        "components": observed,
        "host_snapshot_consistent": discovery_error is None and not warnings,
        "release_verified": False,  # Requires a separate approved-commit + sustained-health attestation.
        "warnings": warnings,
        "authority": "local read-only Windows evidence; GitHub tests are not runtime proof",
    }


def main():
    parser = argparse.ArgumentParser(description="Read-only local host inventory")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--write-local", action="store_true",
                        help="Write only to ignored deploy/state, never GitHub")
    args = parser.parse_args()
    report = collect(args.root)
    if args.write_local:
        registry = validate_registry(args.root, check_local_safety=True)
        p = safe_path(args.root.resolve(), registry["inventory_output"])
        p.parent.mkdir(parents=True, exist_ok=True)
        temp = p.with_suffix(".tmp")
        temp.write_text(json.dumps(report, indent=2), encoding="utf-8")
        temp.replace(p)
    # No raw commands, username, absolute paths, wallets, credentials or secrets.
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
