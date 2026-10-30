"""Offline proof tests for the invested-capital audit, including broker gates."""
import hashlib
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from infrastructure.invested_capital_audit import audit_rows, audit_database, broker_reconcile_today

ET = ZoneInfo("America/New_York")
DAY = "2026-10-28"
OPEN = datetime(2026, 10, 28, 9, 30, tzinfo=ET)
CLOSE = datetime(2026, 10, 28, 16, 0, tzinfo=ET)
AFTER = datetime(2026, 10, 28, 16, 40, tzinfo=ET)


def row(day, at, side, qty, price, order, sym="NVDA"):
    return {
        "ts": datetime.fromisoformat(f"{day}T{at}:00-04:00").isoformat(),
        "side": side, "qty": qty, "price": price,
        "alpaca_order_id": order, "symbol": sym,
    }


def ledger():
    return [
        row("2026-10-27", "10:00", "buy", 10, 100, "b1"),
        row(DAY, "10:30", "buy", 10, 110, "b2"),
        row(DAY, "11:00", "sell", 5, 120, "s1"),
    ]


def pnl():
    return [{"ts": row(DAY, "11:00", "sell", 5, 120, "s1")["ts"], "pnl": 75.0}]


class FakeBroker:
    def __init__(self, *, positions=True, orders=True, flow=0.0, history=True):
        self.positions = positions
        self.orders = orders
        self.flow = flow
        self.history = history

    def get_account(self):
        return SimpleNamespace(id="paper-account", equity=1075, last_equity=1000)

    def get_all_positions(self):
        return [SimpleNamespace(symbol="NVDA", qty="15")] if self.positions else []

    def get_orders(self, filter=None):
        return [
            SimpleNamespace(id=oid, filled_at=when, filled_qty=qty)
            for oid, when, qty in (
                ("b2", datetime(2026, 10, 28, 10, 30, tzinfo=ET), "10"),
                ("s1", datetime(2026, 10, 28, 11, 0, tzinfo=ET), "5"),
            )
        ] if self.orders else []

    def get_portfolio_history(self, request):
        if not self.history:
            return SimpleNamespace(timestamp=[], equity=[], cashflow={})
        old = datetime(2026, 10, 27, 16, 0, tzinfo=ET)
        return SimpleNamespace(
            timestamp=[int(old.timestamp()), int(CLOSE.timestamp())],
            equity=[1000, 1075],
            cashflow={"CSD": [0.0, self.flow]},
        )


class CapitalAuditTests(unittest.TestCase):
    def test_cost_basis_of_closed_lots_and_peak_deployed(self):
        result = audit_rows(ledger(), pnl(), DAY, session_open=OPEN, session_close=CLOSE)
        self.assertEqual(result["status"], "LOCAL_CLOSED_FILLS_RECONCILED_NOT_BROKER_ATTESTED")
        self.assertEqual(result["daily_closed_cost_basis_usd"], 525)
        self.assertEqual(result["daily_reconstructed_realized_pnl_usd"], 75)
        self.assertAlmostEqual(result["daily_closed_invested_capital_return_pct"], 14.285714, 5)
        self.assertEqual(result["peak_session_deployed_cost_usd"], 2100)
        self.assertEqual(result["ledger_end_quantities"], {"NVDA": 15.0})
        self.assertEqual(result["local_session_order_ids"], ["b2", "s1"])
        self.assertEqual(result["first_observed_fill_date"], "2026-10-27")
        self.assertIsNone(result["full_portfolio_inception_return_pct"])
        self.assertFalse(result["broker_reconciled"])

    def test_missing_sell_buy_and_duplicate_order_are_not_metrics(self):
        cases = (
            [ledger()[-1]],
            ledger() + [ledger()[0]],
            [{**ledger()[0], "qty": float("nan")}] + ledger()[1:],
            [{**ledger()[0], "ts": "2026-10-27 10:00:00"}] + ledger()[1:],
        )
        for rows in cases:
            with self.subTest(rows=rows):
                report = audit_rows(rows, pnl(), DAY, session_open=OPEN, session_close=CLOSE)
                self.assertIsNone(report["daily_closed_invested_capital_return_pct"])

    def test_mismatched_local_realized_pnl_fails_closed(self):
        r = audit_rows(ledger(), [{"ts": pnl()[0]["ts"], "pnl": 5.0}], DAY,
                       session_open=OPEN, session_close=CLOSE)
        self.assertEqual(r["status"], "LOCAL_REALIZED_AND_FILLS_RECONCILIATION_FAILED")
        self.assertIsNone(r["daily_closed_invested_capital_return_pct"])

    def test_session_hours_gate_early_close(self):
        result = audit_rows(ledger(), pnl(), DAY, session_open=OPEN,
                            session_close=datetime(2026, 10, 28, 10, 45, tzinfo=ET))
        self.assertEqual(result["status"], "LOCAL_REALIZED_AND_FILLS_RECONCILIATION_FAILED")
        # Unexpected premarket fills cannot be silently included in a
        # regular-session denominator or EOD account reconciliation.
        premarket = ledger() + [row(DAY, "08:45", "buy", 1, 100, "early")]
        r = audit_rows(premarket, pnl(), DAY, session_open=OPEN, session_close=CLOSE)
        self.assertEqual(r["status"], "INVALID_OR_INCOMPLETE_LOCAL_FILL_LEDGER")

    def test_readonly_sqlite_and_corrupt_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = audit_database(Path(tmp) / "missing.sqlite", DAY,
                                     session_open=OPEN, session_close=CLOSE)
            self.assertEqual(missing["status"], "LOCAL_PAPER_FILL_DATABASE_MISSING")
            path = Path(tmp) / "test.sqlite"
            with sqlite3.connect(path) as db:
                db.execute("CREATE TABLE realized (ts TEXT, pnl REAL)")
            report = audit_database(path, DAY, session_open=OPEN, session_close=CLOSE)
            self.assertEqual(report["status"], "LOCAL_PAPER_FILL_DATABASE_UNREADABLE")

    def _broker(self, broker):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "private.json"
            path.write_text(json.dumps({
                "account_key": hashlib.sha256(b"paper-account").hexdigest(),
                "days": {DAY: {
                    "prior_close_equity": 1000, "observed_close_equity": 1075
                }},
            }))
            audited = audit_rows(ledger(), pnl(), DAY, session_open=OPEN, session_close=CLOSE)
            return broker_reconcile_today(
                audited, DAY, history_path=path, session_open=OPEN,
                session_close=CLOSE, now=AFTER,
                client_factory=lambda: broker,
                orders_request_factory=lambda **kwargs: kwargs,
                history_request_factory=lambda **kwargs: kwargs,
            )

    def test_full_daily_invested_roi_requires_broker_crosschecks(self):
        result = self._broker(FakeBroker())
        self.assertEqual(result["daily_invested_capital_return_status"],
                         "MODELED_PAPER_RETURN_ON_PEAK_DEPLOYED_COST")
        self.assertAlmostEqual(result["daily_invested_capital_return_pct"], 3.571429, 5)
        self.assertTrue(result["broker_reconciled"])
        self.assertTrue(result["cash_flows_reconciled"])

    def test_cashflow_orders_positions_or_history_mismatches_block_portfolio_roi(self):
        for settings in (
            {"flow": 500}, {"orders": False}, {"positions": False},
            {"history": False},
        ):
            with self.subTest(settings=settings):
                report = self._broker(FakeBroker(**settings))
                self.assertIsNone(report["daily_invested_capital_return_pct"])
                self.assertFalse(report["broker_reconciled"])
                self.assertIsNotNone(report["daily_closed_invested_capital_return_pct"])

    def test_allowlisted_broker_failure_codes_never_leak_provider_errors(self):
        for settings, expected in (
            ({"positions": False}, "BROKER_POSITIONS_NOT_RECONCILED"),
            ({"orders": False}, "BROKER_FILLS_NOT_OBSERVED"),
            ({"flow": 500}, "BROKER_CASHFLOW_NOT_ZERO"),
            ({"history": False}, "BROKER_HISTORY_DAY_NOT_UNIQUE"),
        ):
            with self.subTest(settings=settings):
                result = self._broker(FakeBroker(**settings))
                self.assertEqual(result["broker_reconciliation_blocker"], expected)
                self.assertIsNone(result["daily_invested_capital_return_pct"])
                self.assertFalse(result["broker_reconciled"])

        class UnsafeBroker(FakeBroker):
            def get_account(self):
                raise ValueError("PRIVATE_BROKER_ERROR_WITH_TOKEN_ABC")

        result = self._broker(UnsafeBroker())
        self.assertEqual(result["broker_reconciliation_blocker"],
                         "BROKER_EVIDENCE_INCOMPLETE_OR_UNRECONCILED")
        self.assertNotIn("PRIVATE_BROKER_ERROR", json.dumps(result))
        self.assertEqual(self._broker(FakeBroker())["broker_reconciliation_blocker"], "NONE")

    def test_no_broker_backdate(self):
        audited = audit_rows(ledger(), pnl(), DAY, session_open=OPEN, session_close=CLOSE)
        result = broker_reconcile_today(
            audited, DAY, history_path=Path("not_read"), session_open=OPEN,
            session_close=CLOSE, now=datetime(2026, 10, 29, 16, 40, tzinfo=ET),
            client_factory=lambda: self.fail("Must not call broker for a stale date"),
        )
        self.assertEqual(result["daily_invested_capital_return_status"], "DATE_NOT_CURRENT")


if __name__ == "__main__":
    unittest.main()
