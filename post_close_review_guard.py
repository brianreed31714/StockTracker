#!/usr/bin/env python3
"""Idempotency guard for the post-close StockTracker review pipeline."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dotenv import load_dotenv
from zoneinfo import ZoneInfo

from post_close_review_policy import review_retry_decision

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env.config')
load_dotenv(ROOT / '.env', override=True)
_runtime_setting = os.getenv("STOCKTRACKER_RUNTIME_ROOT", "").strip()
RUNTIME_ROOT = Path(_runtime_setting).expanduser().resolve() if _runtime_setting else ROOT
if _runtime_setting and (RUNTIME_ROOT == ROOT or ROOT in RUNTIME_ROOT.parents):
    raise ValueError("STOCKTRACKER_RUNTIME_ROOT must be outside the source repository")
STATE_PATH = RUNTIME_ROOT / "post_close_review_state.json"
# Compatibility mirror: existing v1.10 trader reads this path to avoid repeat runs.
LEGACY_STATE_PATH = ROOT / "post_close_review_state.json"
LOCK_PATH = RUNTIME_ROOT / "deploy" / "state" / "post_close_review_guard.lock"
MARKET_TZ = ZoneInfo("America/New_York")


@contextmanager
def exclusive_state():
    """Cross-process lock for trader and Scheduled Task begin/fail/complete.

    Lock metadata contains no credentials. Never read or modify brokerage
    positions, process IDs, or Windows task registration.
    """
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("a+b") as handle:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def read_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_state(value: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = STATE_PATH.with_suffix(".json.tmp")
    temp.write_text(json.dumps(value, indent=2), encoding="utf-8")
    os.replace(temp, STATE_PATH)
    if LEGACY_STATE_PATH != STATE_PATH:
        legacy_tmp = LEGACY_STATE_PATH.with_suffix(".json.tmp")
        legacy_tmp.write_text(json.dumps(value, indent=2), encoding="utf-8")
        os.replace(legacy_tmp, LEGACY_STATE_PATH)


def parse_ts(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=MARKET_TZ)
    except Exception:
        return None


def begin(date_text: str) -> int:
    # Both the trader's +5m path and the scheduled 1:30pm task use this
    # same budget. Do not allow two simultaneous processes to increment it.
    with exclusive_state():
        state = read_state()
        decision = review_retry_decision(state, date_text)
        if decision["action"] == "SKIP":
            reason = decision["reason"]
            print(f"Post-close review not launched: {reason} ({decision['attempts']} attempts).")
            return 21 if reason in {"RETRY_LIMIT", "INVALID_ATTEMPT_COUNT"} else 20
        if decision["action"] == "WAIT":
            print(f"Post-close review cooling down ({decision['attempts']} attempts).")
            return 22

        attempts = decision["attempts"] + 1
        write_state({
            "review_date": date_text,
            "status": "RUNNING",
            "attempts": attempts,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "pid": os.getpid(),
        })
    print(f"Post-close review lock acquired for {date_text}; attempt {attempts}.")
    return 0


def finish(date_text: str, status: str, error: str | None = None,
           stage: str | None = None) -> int:
    with exclusive_state():
        state = read_state()
        if state.get("review_date") != date_text or state.get("status") != "RUNNING":
            print(f"Cannot complete review {date_text}: no matching RUNNING lock.")
            return 1
        state.update({
            "review_date": date_text,
            "status": status,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        })
        if status == "FAILED":
            state["error"] = (error or "review pipeline failed")[:1000]
            state["failure_stage"] = stage or "UNKNOWN"
        else:
            state.pop("error", None)
            state.pop("failure_stage", None)
        write_state(state)
    print(f"Post-close review status for {date_text}: {status}" +
          (f", stage {stage}" if status == "FAILED" and stage else ""))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("begin", "complete", "fail"))
    parser.add_argument("--date", default=datetime.now(MARKET_TZ).date().isoformat())
    parser.add_argument("--error")
    parser.add_argument("--stage", choices=(
        "bundle", "evidence", "model_review", "proposal_publish", "github_sync",
        "guard_complete", "unknown",
    ), default="unknown")
    args = parser.parse_args()

    if args.action == "begin":
        raise SystemExit(begin(args.date))
    if args.action == "complete":
        raise SystemExit(finish(args.date, "COMPLETED"))
    raise SystemExit(finish(args.date, "FAILED", args.error or "pipeline failed", args.stage))


if __name__ == "__main__":
    main()
