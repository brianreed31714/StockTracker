"""Read-only, dependency-light ZPTA dashboard helpers.

Display actual feed errors without leaking provider responses or API credentials.
Forecast dates are Eastern *resolution* dates, not UTC timestamps or creation dates.
Never imports the ZPTA specialist or broker clients and never places orders.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from urllib.parse import quote
from zoneinfo import ZoneInfo

MARKET_TZ = ZoneInfo("America/New_York")


def market_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        # The source DB stores timestamps in UTC; treat legacy naive values as UTC.
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(MARKET_TZ)
    except (ValueError, OverflowError):
        return None


def resolution_market_date(value: object) -> str | None:
    dt = market_datetime(value)
    return dt.date().isoformat() if dt else None


def market_timestamp_label(value: object) -> str:
    dt = market_datetime(value)
    return dt.strftime("%Y-%m-%d %I:%M %p %Z") if dt else "Unknown"


def explain_zpta_status(snapshot: dict) -> str | None:
    """One stable, actionable explanation; raw exception strings stay private."""
    if str(snapshot.get("status") or "").upper() != "ERROR":
        return None
    detail = str(snapshot.get("error") or "").lower()
    if "need at least 10 current-session trade bars" in detail:
        return "Waiting for at least 10 current-session minute bars after the market opens."
    if "429" in detail or "too many requests" in detail or "rate limit" in detail:
        return "ZPTA market-data requests were rate-limited. Check the feed after its cooldown."
    if "403" in detail or "forbidden" in detail or "entitlement" in detail:
        return "ZPTA market-data access was denied. Check OTC entitlement and the Yahoo fallback."
    if "401" in detail or "unauthorized" in detail or "authentication" in detail:
        return "ZPTA market-data authentication failed. Check the provider configuration."
    if ("no bars" in detail or "no one-minute bars" in detail or
            "no current-session" in detail or "returned no" in detail):
        return "No usable ZPTA minute bars were available. Data feeds may be delayed or unavailable."
    if "database is locked" in detail or "sqlite" in detail:
        return "ZPTA could not update its local evidence database. Check concurrent DB access."
    if not detail:
        return "The trader reported a ZPTA error without details; inspect its local logs."
    return "The ZPTA cycle failed; the trader saved a diagnostic in the local dashboard state. Check its local log."


def _read_only_connection(db_path: Path) -> sqlite3.Connection:
    """SQLite URI read-only mode prevents dashboard from creating or altering files."""
    pathname = quote(db_path.resolve().as_posix(), safe="/:")
    return sqlite3.connect(f"file:{pathname}?mode=ro", uri=True, timeout=3)


def daily_resolved_forecasts(db_path: Path, *, max_groups: int = 300) -> list[dict]:
    """Daily performance grouped by the ET date each prediction was resolved.

    Limit only *after* aggregation; never truncate source samples before AVG.
    """
    if max_groups < 1 or max_groups > 2000:
        raise ValueError("max_groups must be between 1 and 2000")
    if not db_path.is_file():
        return []
    with closing(_read_only_connection(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        conn.create_function("resolution_market_date", 1, resolution_market_date)
        cursor = conn.execute(
            """
            SELECT resolution_market_date(resolved_ts) AS market_date,
                   model, horizon_minutes, COUNT(*) AS samples,
                   ROUND(AVG(correct)*100,1) AS accuracy_pct,
                   ROUND(AVG(forward_return)*100,3) AS avg_return_pct
            FROM zpta_predictions
            WHERE resolved_ts IS NOT NULL
              AND resolution_market_date(resolved_ts) IS NOT NULL
            GROUP BY market_date, model, horizon_minutes
            ORDER BY market_date DESC, model, horizon_minutes
            LIMIT ?
            """,
            (max_groups,),
        )
        return [dict(row) for row in cursor.fetchall()]


def all_time_resolved_forecasts(db_path: Path) -> list[dict]:
    """Retain existing lifetime model metrics alongside the dated detail."""
    if not db_path.is_file():
        return []
    with closing(_read_only_connection(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            SELECT model, horizon_minutes, COUNT(*) AS samples,
                   ROUND(AVG(correct)*100,1) AS accuracy_pct,
                   ROUND(AVG(forward_return)*100,3) AS avg_return_pct
            FROM zpta_predictions
            WHERE resolved_ts IS NOT NULL
            GROUP BY model,horizon_minutes
            ORDER BY model,horizon_minutes
            """
        )
        return [dict(row) for row in cursor.fetchall()]


def latest_observation(db_path: Path) -> dict | None:
    """Most recent stored quote is historical evidence, never a live quote."""
    if not db_path.is_file():
        return None
    with closing(_read_only_connection(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT ts,provider,price FROM zpta_observations ORDER BY ts DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None
