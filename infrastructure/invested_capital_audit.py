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


def broker_reconcile_today(audit, day, *, history_path, session_open, session_close, now=None, client_factory=None):
    """Optional read-only cross-check with PAPER Alpaca, never changes orders.

    A daily account P/L / peak deployed *cost* basis percentage is eligible
    only if historical prices/equity, paper position quantities, ALL paper
    closed filled orders and explicit zero cashflow agree with the local
    complete fill ledger. Any absent, truncated or mismatched broker source
    blocks that metric, but preserves the separate closed-trade ROI.
    """
    result = dict(audit)
    result["broker_reconciled"] = False
    result["daily_invested_capital_return_pct"] = None
    result["daily_invested_capital_return_status"] = "BROKER_RECONCILIATION_MISSING"
    result["cash_flows_reconciled"] = False
    if audit.get("status") != "LOCAL_CLOSED_FILLS_RECONCILED_NOT_BROKER_ATTESTED":
        return result
    base = number(audit.get("peak_session_deployed_cost_usd"), positive=True)
    if base is None:
        result["daily_invested_capital_return_status"] = "ZERO_OR_UNVERIFIED_DEPLOYED_CAPITAL"
        return result
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None or now.astimezone(EASTERN).date().isoformat() != day:
        result["daily_invested_capital_return_status"] = "DATE_NOT_CURRENT"
        return result
    if now < session_close:
        result["daily_invested_capital_return_status"] = "SESSION_NOT_CLOSED"
        return result
    try:
        from datetime import timedelta
        import json
        import os
        from alpaca.trading.client import TradingClient
        from alpaca.trading.requests import GetOrdersRequest, GetPortfolioHistoryRequest
        from alpaca.trading.enums import QueryOrderStatus

        key = os.getenv("ALPACA_API_KEY", "").strip()
        secret = os.getenv("ALPACA_SECRET_KEY", "").strip()
        if client_factory is None:
            if not key or not secret:
                raise ValueError("PAPER_BROKER_CREDENTIALS_MISSING")
            client_factory = lambda: TradingClient(key, secret, paper=True)
        client = client_factory()
        account = client.get_account()
        prior = number(getattr(account, "last_equity", None), positive=True)
        current = number(getattr(account, "equity", None), positive=True)
        account_id = str(getattr(account, "id", "") or "")
        if not account_id or prior is None or current is None:
            raise ValueError("BROKER_EQUITY_MISSING")
        import hashlib
        account_hash = hashlib.sha256(account_id.encode("utf-8")).hexdigest()
        saved = json.loads(Path(history_path).read_text(encoding="utf-8"))
        if saved.get("account_key") != account_hash:
            raise ValueError("ACCOUNT_SCOPE_MISMATCH")
        entry = (saved.get("days") or {}).get(day) or {}
        if (abs(float(entry.get("prior_close_equity", -1)) - prior) > 0.02 or
                abs(float(entry.get("observed_close_equity", -1)) - current) > 0.02):
            raise ValueError("DATED_EQUITY_SNAPSHOT_MISMATCH")

        # The local ledger is a whole-account source only if independently
        # observed PAPER account positions and broker filled orders match.
        actual = {}
        for pos in client.get_all_positions():
            qty = number(getattr(pos, "qty", None))
            symbol = str(getattr(pos, "symbol", "") or "")
            if not symbol or qty is None:
                raise ValueError("BROKER_POSITION_INVALID")
            if qty > 1e-7:
                actual[symbol] = qty
        expected = audit.get("ledger_end_quantities") or {}
        if set(actual) != set(expected) or any(
            abs(actual[symbol] - expected[symbol]) > 0.000001
            for symbol in actual
        ):
            raise ValueError("BROKER_POSITIONS_NOT_RECONCILED")

        # The Alpaca request filters by submission time rather than fill time.
        # Fetch a broad enough window; if the single response reaches the
        # pagination limit, refuse to treat the coverage as complete.
        request = GetOrdersRequest(
            status=QueryOrderStatus.CLOSED,
            after=session_open - timedelta(days=14),
            until=now,
            limit=500,
        )
        orders = client.get_orders(filter=request)
        if not isinstance(orders, list) or len(orders) >= 500:
            raise ValueError("BROKER_ORDER_HISTORY_TRUNCATED")
        broker_ids = set()
        for order in orders:
            filled_at = getattr(order, "filled_at", None)
            qty = number(getattr(order, "filled_qty", None))
            if not isinstance(filled_at, datetime) or filled_at.tzinfo is None or qty is None or qty <= 0:
                continue
            if session_open <= filled_at <= session_close:
                broker_ids.add(str(getattr(order, "id", "") or ""))
        if not broker_ids and audit.get("observed_daily_sell_count", 0) > 0:
            raise ValueError("BROKER_FILLS_NOT_OBSERVED")
        # Broker IDs are compared to a second read-only local SQLite fetch by
        # the caller; this audit only records a positive count when supplied.
        local_ids = audit.get("local_session_order_ids") or []
        if set(broker_ids) != set(local_ids):
            raise ValueError("BROKER_AND_LOCAL_FILL_IDS_MISMATCH")

        # Check the dated 1D account-history point. Request ALL cashflow types;
        # absent history, invalid arrays, or any nonzero reported cash movement
        # fail closed rather than deducting an unverified transfer.
        history = client.get_portfolio_history(GetPortfolioHistoryRequest(
            start=session_open - timedelta(days=14), end=now,
            timeframe="1D", cashflow_types="ALL",
        ))
        stamps = getattr(history, "timestamp", None)
        values = getattr(history, "equity", None)
        flows = getattr(history, "cashflow", None)
        if not isinstance(stamps, list) or not isinstance(values, list) or len(stamps) != len(values):
            raise ValueError("BROKER_PORTFOLIO_HISTORY_MISSING")
        if not isinstance(flows, dict):
            raise ValueError("BROKER_CASHFLOW_COVERAGE_MISSING")
        dated = []
        for index, stamp in enumerate(stamps):
            if isinstance(stamp, bool):
                raise ValueError("BROKER_HISTORY_TIMESTAMP_INVALID")
            when = datetime.fromtimestamp(int(stamp), timezone.utc).astimezone(EASTERN)
            if when.date().isoformat() == day:
                dated.append(index)
        if len(dated) != 1:
            raise ValueError("BROKER_HISTORY_DAY_NOT_UNIQUE")
        index = dated[0]
        historical_equity = number(values[index], positive=True)
        if historical_equity is None or abs(historical_equity - current) > 1.01:
            raise ValueError("BROKER_HISTORY_CLOSE_MISMATCH")
        for array in flows.values():
            if not isinstance(array, (list, tuple)) or len(array) != len(stamps):
                raise ValueError("BROKER_CASHFLOW_SHAPE_INVALID")
            amount = array[index]
            if isinstance(amount, bool):
                raise ValueError("BROKER_CASHFLOW_VALUE_INVALID")
            try:
                amount = float(amount)
            except (TypeError, ValueError, OverflowError):
                raise ValueError("BROKER_CASHFLOW_VALUE_INVALID")
            if not math.isfinite(amount) or abs(amount) > 0.005:
                raise ValueError("BROKER_CASHFLOW_NOT_ZERO")

        pnl = current - prior
        result["broker_reconciled"] = True
        result["cash_flows_reconciled"] = True
        result["daily_invested_capital_return_pct"] = round(100.0 * pnl / base, 6)
        result["daily_invested_capital_return_status"] = "MODELED_PAPER_RETURN_ON_PEAK_DEPLOYED_COST"
        result["broker_account_pnl_usd"] = round(pnl, 4)
        return result
    except (OSError, RuntimeError, TypeError, ValueError, AttributeError, ImportError, OverflowError, IndexError):
        # Never log or publish broker exception text, account IDs, order IDs,
        # raw equity, position inventory or API credentials.
        result["daily_invested_capital_return_status"] = "BROKER_EVIDENCE_INCOMPLETE_OR_UNRECONCILED"
        return result
