"""Read-only, fail-closed observation of the named Windows EOD scheduled task.

Task Scheduler success is NOT proof of a fresh report, a Pushover receipt,
device delivery, loaded trader code, or trading correctness.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from typing import Callable

TASK_NAME = "StockTracker Daily Review"
ALLOWED_STATES = {"Ready", "Running", "Disabled", "Queued", "Unknown"}


def inspect_daily_review_task(*, clock: datetime | None = None,
                              runner: Callable | None = None) -> dict:
    unavailable = {"status": "UNVERIFIED", "reason": "TASK_SCHEDULER_EVIDENCE_UNAVAILABLE"}
    if runner is None and os.name != "nt":
        return unavailable
    now = clock or datetime.now(timezone.utc)
    if now.tzinfo is None:
        return unavailable
    # Fixed task name and fixed PowerShell expression; no external/user input.
    script = (
        "$ErrorActionPreference='Stop';"
        "$t=Get-ScheduledTask -TaskName 'StockTracker Daily Review' -ErrorAction Stop;"
        "$i=Get-ScheduledTaskInfo -TaskName 'StockTracker Daily Review' -ErrorAction Stop;"
        "$last=if($i.LastRunTime.Year -gt 2000)"
        "{$i.LastRunTime.ToUniversalTime().ToString('o')}else{$null};"
        "[pscustomobject]@{state=[string]$t.State;last_run_utc=$last;"
        "last_result=[long]$i.LastTaskResult}|ConvertTo-Json -Compress"
    )
    try:
        command = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script]
        response = (runner or subprocess.run)(
            command, capture_output=True, text=True, timeout=12
        )
        if response.returncode != 0 or len(response.stdout) > 4096:
            return unavailable
        data = json.loads(response.stdout)
        if not isinstance(data, dict) or data.get("state") not in ALLOWED_STATES:
            return unavailable
        result = data.get("last_result")
        if type(result) is not int or not (-2**31 <= result < 2**32):
            return unavailable
        raw = data.get("last_run_utc")
        last = None
        if raw is not None:
            if not isinstance(raw, str):
                return unavailable
            last = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if last.tzinfo is None or last.year < 2001 or last > now:
                return unavailable
            last = last.astimezone(timezone.utc).isoformat()
        return {
            "status": "TASK_NAME_OBSERVED",
            "scheduler_state": data["state"],
            "last_run_utc": last,
            "last_task_result": result,
            "eod_delivery_verified": False,
        }
    except (OSError, ValueError, TypeError, KeyError, subprocess.TimeoutExpired):
        return unavailable
