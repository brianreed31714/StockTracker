"""Broker historical coverage gates for modeled PAPER since-first-fill ROI."""
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from infrastructure.invested_capital_audit import audit_rows, observed_history_curve

ET = ZoneInfo("America/New_York")
DAY = "2026-10-28"
OPEN = datetime(2026, 10, 28, 9, 30, tzinfo=ET)
CLOSE = datetime(2026, 10, 28, 16, tzinfo=ET)
NOW = datetime(2026, 10, 28, 16, 40, tzinfo=ET)


def fill(day, hour, side, qty, price, oid):
    return {"ts": datetime.fromisoformat(f"{day}T{hour}:00-04:00").isoformat(),
            "symbol": "NVDA", "side": side, "qty": qty, "price": price,
            "alpaca_order_id": oid}


def ledger():
    rows = [
        fill("2026-10-27", "10:00", "buy", 10, 100, "b1"),
        fill(DAY, "10:30", "buy", 10, 110, "b2"),
        fill(DAY, "11:00", "sell", 5, 120, "s1"),
    ]
    return audit_rows(rows, [{"ts": rows[-1]["ts"], "pnl": 75}], DAY,
                      session_open=OPEN, session_close=CLOSE)


class HistoricalBroker:
    def __init__(self, *, missing_order=False, missing_session=False,
                 external_flow=0, interim_value=1000):
        self.missing_order = missing_order
        self.missing_session = missing_session
        self.external_flow = external_flow
        self.interim_value = interim_value

    def get_orders(self, filter=None):
        records = [
            ("b1", datetime(2026, 10, 27, 10, tzinfo=ET), "10"),
            ("b2", datetime(2026, 10, 28, 10, 30, tzinfo=ET), "10"),
            ("s1", datetime(2026, 10, 28, 11, tzinfo=ET), "5"),
        ]
        if self.missing_order:
            records = records[1:]
        return [SimpleNamespace(id=i, filled_at=d, filled_qty=q)
                for i, d, q in records]

    def get_portfolio_history(self, history_filter):
        days = [datetime(2026, 10, d, 16, tzinfo=ET)
                for d in (26, 27, 28)]
        return SimpleNamespace(
            timestamp=[int(d.timestamp()) for d in days],
            equity=[1000, self.interim_value, 1075],
            cashflow={"CSD": [0, self.external_flow, 0]},
        )

    def get_calendar(self, filter):
        dates = (27,) if self.missing_session else (27, 28)
        return [SimpleNamespace(date=f"2026-10-{d}") for d in dates]


class CurveTests(unittest.TestCase):
    def calculate(self, broker):
        return observed_history_curve(
            ledger(), day=DAY, now=NOW, client=broker,
            orders_request_factory=lambda **kwargs: kwargs,
            history_request_factory=lambda **kwargs: kwargs,
            calendar_request_factory=lambda **kwargs: kwargs,
        )

    def test_return_and_drawdown_from_broker_complete_first_fill_window(self):
        x = self.calculate(HistoricalBroker(interim_value=950))
        self.assertAlmostEqual(x["since_first_recorded_fill_portfolio_return_pct"], 3.571429, 5)
        self.assertAlmostEqual(x["since_first_recorded_fill_portfolio_drawdown_pct"], 2.380952, 5)
        self.assertEqual(x["since_first_recorded_fill_sessions"], 2)
        self.assertEqual(x["inception_basis_status"], "OBSERVED_FIRST_FILL_ONLY")
        self.assertIsNone(x["since_inception_invested_return_pct"])

    def test_explicit_inception_date_required_to_use_inception_label(self):
        with patch.dict("os.environ", {"STOCKTRACKER_STRATEGY_INCEPTION_DATE": "2026-10-27"}):
            x = self.calculate(HistoricalBroker())
        self.assertEqual(x["inception_basis_status"],
                         "CONFIGURED_START_EQUALS_FIRST_FILL_WITH_BROKER_COVERAGE")
        self.assertAlmostEqual(x["since_inception_invested_return_pct"], 3.571429, 5)
        self.assertEqual(x["since_inception_invested_drawdown_pct"], 0.0)

    def test_other_configured_inception_date_does_not_forge_history(self):
        with patch.dict("os.environ", {"STOCKTRACKER_STRATEGY_INCEPTION_DATE": "2026-10-09"}):
            x = self.calculate(HistoricalBroker())
        self.assertEqual(x["inception_basis_status"], "OBSERVED_FIRST_FILL_ONLY")
        self.assertIsNone(x["since_inception_invested_return_pct"])

    def test_any_missing_order_session_or_cashflow_fails_entire_window(self):
        for change in (
            {"missing_order": True},
            {"missing_session": True},
            {"external_flow": 2.50},
        ):
            with self.subTest(change=change):
                x = self.calculate(HistoricalBroker(**change))
                self.assertIsNone(x["since_first_recorded_fill_portfolio_return_pct"])
                self.assertIsNone(x["since_first_recorded_fill_portfolio_drawdown_pct"])
                self.assertIsNone(x["since_inception_invested_return_pct"])


if __name__ == "__main__":
    unittest.main()
