"""Pure, side-effect-free retry policy shared by the StockTracker review guard
and paper trader. No brokerage clients, process manipulation, or network calls.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

MAX_ATTEMPTS_PER_SESSION = 3
FAILED_RETRY_COOLDOWN_MINUTES = 15
RUNNING_LOCK_STALE_MINUTES = 45


def parse_utc_timestamp(value: Any) -> datetime | None:
    if value is None or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return None
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def review_retry_decision(
    state: dict,
    review_date: str,
    *,
    now: datetime | None = None,
) -> dict:
    """Return action RUN, WAIT, or SKIP and a stable non-secret reason.

    Unknown or malformed state fails closed for an in-progress review.
    A new trading session has a fresh three-attempt budget.
    """
    if not isinstance(state, dict):
        state = {}
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Review retry clock requires an aware datetime")
    now = now.astimezone(timezone.utc)
    if state.get("review_date") != review_date:
        return {"action": "RUN", "reason": "NEW_SESSION", "attempts": 0,
                "next_attempt_utc": None}

    try:
        attempts = max(0, int(state.get("attempts") or 0))
    except (TypeError, ValueError, OverflowError):
        return {"action": "SKIP", "reason": "INVALID_ATTEMPT_COUNT",
                "attempts": 0, "next_attempt_utc": None}

    status = str(state.get("status") or "").upper()
    if status == "COMPLETED":
        return {"action": "SKIP", "reason": "COMPLETED",
                "attempts": attempts, "next_attempt_utc": None}
    if status == "RUNNING":
        started = parse_utc_timestamp(state.get("started_at"))
        if started is None:
            return {"action": "SKIP", "reason": "RUNNING_TIME_UNVERIFIED",
                    "attempts": attempts, "next_attempt_utc": None}
        if now - started < timedelta(minutes=RUNNING_LOCK_STALE_MINUTES):
            return {"action": "SKIP", "reason": "ALREADY_RUNNING",
                    "attempts": attempts, "next_attempt_utc": None}

    if attempts >= MAX_ATTEMPTS_PER_SESSION:
        return {"action": "SKIP", "reason": "RETRY_LIMIT",
                "attempts": attempts, "next_attempt_utc": None}

    if status == "FAILED":
        finished = parse_utc_timestamp(state.get("finished_at"))
        if finished is None:
            return {"action": "SKIP", "reason": "FAILED_TIME_UNVERIFIED",
                    "attempts": attempts, "next_attempt_utc": None}
        retry_at = finished + timedelta(minutes=FAILED_RETRY_COOLDOWN_MINUTES)
        if now < retry_at:
            return {"action": "WAIT", "reason": "COOLDOWN",
                    "attempts": attempts, "next_attempt_utc": retry_at}

    return {"action": "RUN", "reason": "ELIGIBLE", "attempts": attempts,
            "next_attempt_utc": None}
