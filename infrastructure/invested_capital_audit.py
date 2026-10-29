"""Conservative, read-only cost-basis ROI audit of StockTracker PAPER fills.

This is NOT account-level portfolio return: open-position mark-to-market, cash
flows, and broker completeness require independent reconciliation. It reports a
useful percentage of capital actually invested in positions that were CLOSED,
and an observed-history counterpart. All numbers are from PAPER local SQLite
fills with moving-average cost basis (matching the trader's sync_fills).
"""
from __future__ import annotations

import math
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")
SOURCE = "LOCAL_PAPER_FILLED_ORDERS_MOVING_AVERAGE"


def number(value, *, positive=False):
    if isinstance(value, bool):
        return None
    try:
        n = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(n) or n < 0 or (positive and n <= 0):
        return None
    return n


def percent(numerator, denominator):
    if denominator is None or denominator <= 0 or numerator is None:
        return None
    n = 100.0 * numerator / denominator
    return round(n, 6) if math.isfinite(n) else None


def unavailable(day, reason):
    return {
        "review_date": day,
        "source": SOURCE,
        "status": reason,
        "daily_closed_invested_capital_return_pct": None,
        "daily_closed_cost_basis_usd": None,
        "daily_reconstructed_realized_pnl_usd": None,
        "observed_fills_closed_invested_return_pct": None,
        "observed_fills_closed_cost_basis_usd": None,
        "observed_fills_realized_pnl_usd": None,
        "peak_session_deployed_cost_usd": None,
        "first_observed_fill_date": None,
        "fill_records_observed": 0,
        "observed_daily_sell_count": 0,
        "ledger_end_quantities": {},
        "broker_reconciled": False,
        "full_portfolio_daily_roi_pct": None,
        "full_portfolio_inception_return_pct": None,
    }


def _timestamp(value):
    if not isinstance(value, str):
        raise ValueError("Timestamp invalid")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("Naive fill timestamp")
    return stamp.astimezone(timezone.utc)


def _date(value):
    d = date.fromisoformat(value)
    if d.isoformat() != value:
        raise ValueError("Date noncanonical")
    return d


def audit_rows(fills, realized_rows, day, *, session_open, session_close):
    """Rebuild a moving-average ledger from ALL recorded fills up to day end.

    Do not treat the observed history as system inception; a historical broker
    completeness check and proven baseline are separately required.
    """
    try:
        _date(day)
        if session_open.tzinfo is None or session_close.tzinfo is None or session_close <= session_open:
            raise ValueError("Invalid exchange hours")
        if session_open.astimezone(EASTERN).date().isoformat() != day:
            raise ValueError("Wrong market session")
        if session_close.astimezone(EASTERN).date().isoformat() != day:
            raise ValueError("Wrong market close")
        entries = []
        ids = set()
        for row in fills:
            when = _timestamp(row.get("ts"))
            if when > session_close.astimezone(timezone.utc):
                continue
            symbol = row.get("symbol")
            side = str(row.get("side") or "").lower()
            qty = number(row.get("qty"), positive=True)
            price = number(row.get("price"), positive=True)
            order_id = str(row.get("alpaca_order_id") or "")
            if not isinstance(symbol, str) or not symbol or side not in {"buy", "sell"}:
                raise ValueError("Invalid fill identity")
            if qty is None or price is None or not order_id or order_id in ids:
                raise ValueError("Missing, duplicated or invalid filled order")
            ids.add(order_id)
            entries.append((when, order_id, symbol, side, qty, price))
        entries.sort(key=lambda r: (r[0], r[1]))
        if not entries:
            return unavailable(day, "NO_RECORDED_FILLS")

        inventory = {}
        max_cost = 0.0
        day_basis = day_pnl = total_basis = total_pnl = 0.0
        day_sells = 0
        first = entries[0][0].astimezone(EASTERN).date().isoformat()
        for when, _, symbol, side, qty, price in entries:
            current_qty, cost = inventory.get(symbol, (0.0, 0.0))
            current_day = when.astimezone(EASTERN).date().isoformat()
            if current_day == day and not session_open <= when <= session_close:
                raise ValueError("Out-of-session fill affects daily equity")
            if side == "buy":
                inventory[symbol] = (current_qty + qty, cost + qty * price)
            else:
                if current_qty < qty - 1e-7:
                    raise ValueError("Incomplete historical buy/short ledger")
                sold = min(qty, current_qty)
                sold_cost = (cost / current_qty) * sold
                pnl = sold * price - sold_cost
                remaining = max(0.0, current_qty - sold)
                inventory[symbol] = (remaining, max(0.0, cost - sold_cost) if remaining > 1e-8 else 0.0)
                total_basis += sold_cost
                total_pnl += pnl
                if current_day == day:
                    day_basis += sold_cost
                    day_pnl += pnl
                    day_sells += 1
            if session_open <= when <= session_close:
                max_cost = max(max_cost, sum(v[1] for v in inventory.values()))

        # Carry-in positions count even if there are no new buys today.
        carried = {}
        for when, _, symbol, side, qty, price in entries:
            if when >= session_open:
                break
            q, cost = carried.get(symbol, (0.0, 0.0))
            if side == "buy":
                carried[symbol] = (q + qty, cost + qty * price)
            else:
                if q < qty - 1e-7:
                    raise ValueError("Incomplete opening holdings")
                closed_cost = cost / q * qty
                carried[symbol] = (max(0.0, q - qty), max(0.0, cost - closed_cost))
        max_cost = max(max_cost, sum(v[1] for v in carried.values()))

        recorded = []
        for row in realized_rows:
            when = _timestamp(row.get("ts"))
            if when.astimezone(EASTERN).date().isoformat() != day:
                continue
            amount = row.get("pnl")
            if isinstance(amount, bool):
                raise ValueError("Invalid local realized P/L")
            try:
                amount = float(amount)
            except (TypeError, ValueError, OverflowError):
                raise ValueError("Invalid local realized P/L")
            if not math.isfinite(amount):
                raise ValueError("Invalid local realized P/L")
            recorded.append(amount)
        if len(recorded) != day_sells or abs(sum(recorded) - day_pnl) > 0.03 + 0.01 * day_sells:
            return unavailable(day, "LOCAL_REALIZED_AND_FILLS_RECONCILIATION_FAILED")

        result = unavailable(day, "LOCAL_CLOSED_FILLS_RECONCILED_NOT_BROKER_ATTESTED")
        result.update({
            "daily_closed_invested_capital_return_pct": percent(day_pnl, day_basis),
            "daily_closed_cost_basis_usd": round(day_basis, 4),
            "daily_reconstructed_realized_pnl_usd": round(day_pnl, 4),
            "observed_fills_closed_invested_return_pct": percent(total_pnl, total_basis),
            "observed_fills_closed_cost_basis_usd": round(total_basis, 4),
            "observed_fills_realized_pnl_usd": round(total_pnl, 4),
            "peak_session_deployed_cost_usd": round(max_cost, 4) if max_cost > 0 else None,
            "first_observed_fill_date": first,
            "fill_records_observed": len(entries),
            "observed_daily_sell_count": day_sells,
            "ledger_end_quantities": {
                symbol: round(values[0], 7) for symbol, values in sorted(inventory.items())
                if values[0] > 1e-7
            },
        })
        return result
    except (ValueError, TypeError, OverflowError, KeyError):
        return unavailable(day, "INVALID_OR_INCOMPLETE_LOCAL_FILL_LEDGER")


def audit_database(db_path, day, *, session_open, session_close):
    """SQLite opened strictly read-only; never creates or mutates a database."""
    path = Path(db_path)
    if not path.is_file():
        return unavailable(day, "LOCAL_PAPER_FILL_DATABASE_MISSING")
    try:
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=6) as db:
            db.row_factory = sqlite3.Row
            fills = [dict(row) for row in db.execute(
                "SELECT ts, symbol, side, qty, price, alpaca_order_id FROM fills ORDER BY ts, alpaca_order_id"
            )]
            realized = [dict(row) for row in db.execute("SELECT ts, pnl FROM realized")]
        return audit_rows(fills, realized, day, session_open=session_open, session_close=session_close)
    except (sqlite3.DatabaseError, sqlite3.OperationalError, OSError):
        return unavailable(day, "LOCAL_PAPER_FILL_DATABASE_UNREADABLE")
