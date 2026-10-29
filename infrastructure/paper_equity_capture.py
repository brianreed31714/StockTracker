"""Read-only Alpaca PAPER account equity observations for StockTracker EOD.

The private local history is ignored by Git. Only percentages, evidence status,
and coverage counts enter the sanitized performance report. This module NEVER
places orders, changes trading settings, or claims realized P/L / exposure is
a full portfolio return.

Alpaca equity vs last_equity is an *unadjusted PAPER account change*, not a
cash-flow-adjusted time-weighted return or return on deployed capital.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")
HISTORY_NAME = "portfolio_account_equity_history.json"
SCHEMA = "stocktracker_paper_account_equity_v1"


def _num(value, *, positive=False):
    if isinstance(value, bool):
        return None
    try:
        amount = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    if not math.isfinite(amount) or (positive and amount <= 0) or amount < 0:
        return None
    return amount


def _pct(after, before):
    if before is None or before <= 0 or after is None:
        return None
    value = (after / before - 1.0) * 100.0
    return round(value, 6) if math.isfinite(value) else None


def _empty(day, reason):
    return {
        "review_date": day,
        "source": "ALPACA_PAPER_ACCOUNT",
        "status": reason,
        "daily_account_change_pct": None,
        "daily_invested_capital_return_pct": None,
        "since_inception_portfolio_return_pct": None,
        "observed_window_account_change_pct": None,
        "observed_window_max_drawdown_pct": None,
        "observed_session_count": 0,
        "cash_flows_reconciled": False,
        "full_portfolio_return_verified": False,
    }


def _read_history(path):
    try:
        obj = json.loads(Path(path).read_text(encoding="utf-8"))
    except (ValueError, OSError, TypeError):
        return {}
    return obj if isinstance(obj, dict) and obj.get("schema") == SCHEMA else {}


def _save_history(path, history):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    candidate = path.with_suffix(".tmp")
    candidate.write_text(json.dumps(history, sort_keys=True, indent=2), encoding="utf-8")
    candidate.replace(path)


def _snapshot_scorecard(day, history):
    entries = history.get("days") or {}
    target = entries.get(day)
    if not isinstance(target, dict):
        return _empty(day, "MISSING_DATED_BROKER_SNAPSHOT")
    start = _num(target.get("prior_close_equity"), positive=True)
    end = _num(target.get("observed_close_equity"), positive=True)
    if start is None or end is None:
        return _empty(day, "INVALID_DATED_BROKER_SNAPSHOT")
    result = _empty(day, "PAPER_ACCOUNT_CHANGE_UNADJUSTED_CASH_FLOWS")
    result["daily_account_change_pct"] = _pct(end, start)
    result["observed_session_count"] = 1
    # Only same-account, chronological, dated close observations can form a
    # partial curve. No extrapolation across missing sessions or cash flows.
    valid = []
    for key in sorted(entries):
        if key > day:
            continue
        item = entries[key]
        if not isinstance(item, dict):
            continue
        try:
            if date.fromisoformat(key).isoformat() != key:
                continue
        except (ValueError, TypeError):
            continue
        value = _num(item.get("observed_close_equity"), positive=True)
        if value is not None:
            valid.append((key, value))
    result["observed_session_count"] = len(valid)
    if len(valid) >= 2:
        first = valid[0][1]
        last = valid[-1][1]
        result["observed_window_account_change_pct"] = _pct(last, first)
        peak = first
        deepest = 0.0
        for _, value in valid[1:]:
            peak = max(peak, value)
            deepest = max(deepest, (peak - value) / peak * 100.0)
        result["observed_window_max_drawdown_pct"] = round(deepest, 6)
    return result


def _calendar_close(client, day):
    """Exchange calendar determines close, including early closes and holidays."""
    from alpaca.trading.requests import GetCalendarRequest

    session = date.fromisoformat(day)
    days = client.get_calendar(GetCalendarRequest(start=session, end=session))
    for entry in days:
        observed = entry.date
        if isinstance(observed, datetime):
            observed = observed.date()
        if isinstance(observed, str):
            observed = date.fromisoformat(observed)
        if observed != session:
            continue
        closing = entry.close
        if isinstance(closing, str):
            closing = time.fromisoformat(closing)
        if isinstance(closing, datetime):
            closing = closing.timetz()
        if not isinstance(closing, time):
            return None
        return datetime.combine(session, closing.replace(tzinfo=None), tzinfo=EASTERN)
    return None


def collect_for_review(review_date, *, history_path, now=None, client_factory=None):
    """Capture only *today's completed* PAPER session; never backdate equity.

    When reprocessing a past review, return its previously saved observation,
    or explicit MISSING. Treat API/calendar outages as missing evidence without
    blocking the existing trade/research bundle.
    """
    try:
        day = date.fromisoformat(review_date)
        if day.isoformat() != review_date:
            raise ValueError("Noncanonical review date")
    except (ValueError, TypeError):
        return _empty(str(review_date), "INVALID_REVIEW_DATE")

    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        return _empty(review_date, "CLOCK_UNVERIFIED")
    existing = _read_history(history_path)
    current_day = now.astimezone(EASTERN).date()
    if day != current_day:
        return _snapshot_scorecard(review_date, existing)

    key = os.getenv("ALPACA_API_KEY", "").strip()
    secret = os.getenv("ALPACA_SECRET_KEY", "").strip()
    if client_factory is None:
        if not key or not secret:
            return _snapshot_scorecard(review_date, existing) if review_date in (existing.get("days") or {}) else _empty(review_date, "PAPER_ACCOUNT_CREDENTIALS_UNAVAILABLE")
        from alpaca.trading.client import TradingClient
        client_factory = lambda: TradingClient(key, secret, paper=True)
    try:
        client = client_factory()
        close = _calendar_close(client, review_date)
        if close is None:
            return _empty(review_date, "NO_VERIFIED_MARKET_SESSION")
        if now.astimezone(EASTERN) < close + timedelta(minutes=5):
            return _empty(review_date, "MARKET_SESSION_NOT_CLOSED")
        account = client.get_account()  # Read-only; no order methods invoked.
        start = _num(account.last_equity, positive=True)
        end = _num(account.equity, positive=True)
        account_id = str(getattr(account, "id", "") or "")
        if start is None or end is None or not account_id:
            return _empty(review_date, "PAPER_ACCOUNT_EQUITY_OR_ID_UNAVAILABLE")
        account_key = hashlib.sha256(account_id.encode("utf-8")).hexdigest()
        # The private history must never combine separate Alpaca accounts.
        if existing.get("account_key") != account_key:
            existing = {"schema": SCHEMA, "account_key": account_key, "days": {}}
        entries = existing.setdefault("days", {})
        entries[review_date] = {
            "prior_close_equity": start,
            "observed_close_equity": end,
            "observed_at_utc": now.astimezone(timezone.utc).isoformat(),
            "market_close_at_utc": close.astimezone(timezone.utc).isoformat(),
        }
        _save_history(history_path, existing)
        return _snapshot_scorecard(review_date, existing)
    except (OSError, RuntimeError, TypeError, ValueError, AttributeError, ImportError):
        # Never log client exceptions: they may contain sensitive API metadata.
        return _snapshot_scorecard(review_date, existing) if review_date in (existing.get("days") or {}) else _empty(review_date, "PAPER_ACCOUNT_OBSERVATION_UNAVAILABLE")
