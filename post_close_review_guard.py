#!/usr/bin/env python3
"""Idempotency guard for the post-close StockTracker review pipeline."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
_runtime_setting = os.getenv("STOCKTRACKER_RUNTIME_ROOT", "").strip()
RUNTIME_ROOT = Path(_runtime_setting).expanduser().resolve() if _runtime_setting else ROOT
if _runtime_setting and (RUNTIME_ROOT == ROOT or ROOT in RUNTIME_ROOT.parents):
    raise ValueError("STOCKTRACKER_RUNTIME_ROOT must be outside the source repository")
STATE_PATH = RUNTIME_ROOT / "post_close_review_state.json"
MARKET_TZ = ZoneInfo("America/New_York")


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


def parse_ts(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=MARKET_TZ)
    except Exception:
        return None


def begin(date_text: str) -> int:
    state = read_state()
    if state.get("review_date") == date_text and state.get("status") == "COMPLETED":
        print(f"Post-close review already completed for {date_text}.")
        return 20

    started = parse_ts(state.get("started_at"))
    if (
        state.get("review_date") == date_text
        and state.get("status") == "RUNNING"
        and started
        and datetime.now(timezone.utc) - started.astimezone(timezone.utc) < timedelta(minutes=45)
    ):
        print(f"Post-close review already running for {date_text}.")
        return 20

    attempts = int(state.get("attempts") or 0) + 1 if state.get("review_date") == date_text else 1
    write_state({
        "review_date": date_text,
        "status": "RUNNING",
        "attempts": attempts,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "pid": os.getpid(),
    })
    print(f"Post-close review lock acquired for {date_text}; attempt {attempts}.")
    return 0


def finish(date_text: str, status: str, error: str | None = None) -> int:
    state = read_state()
    state.update({
        "review_date": date_text,
        "status": status,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    })
    if error:
        state["error"] = error[:1000]
    else:
        state.pop("error", None)
    write_state(state)
    print(f"Post-close review status for {date_text}: {status}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("begin", "complete", "fail"))
    parser.add_argument("--date", default=datetime.now(MARKET_TZ).date().isoformat())
    parser.add_argument("--error")
    args = parser.parse_args()

    if args.action == "begin":
        raise SystemExit(begin(args.date))
    if args.action == "complete":
        raise SystemExit(finish(args.date, "COMPLETED"))
    raise SystemExit(finish(args.date, "FAILED", args.error or "pipeline failed"))


if __name__ == "__main__":
    main()
