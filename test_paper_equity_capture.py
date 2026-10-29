"""Regression tests: paper-only equity, no backdating, private history."""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from infrastructure import paper_equity_capture as equity

ET = ZoneInfo("America/New_York")


class FakeAccount:
    def __init__(self, previous=100.0, current=104.0, account_id="paper-account-a"):
        self.last_equity = previous
        self.equity = current
        self.id = account_id


class FakeClient:
    def __init__(self, account):
        self.account = account
        self.reads = 0

    def get_account(self):
        self.reads += 1
        return self.account


class PaperEquityTests(unittest.TestCase):
    def test_dated_paper_account_change_is_not_invested_return(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "deploy/state/private.json"
            client = FakeClient(FakeAccount())
            clock = datetime(2026, 10, 28, 16, 30, tzinfo=ET)
            close = datetime(2026, 10, 28, 16, 0, tzinfo=ET)
            with patch.object(equity, "_calendar_close", return_value=close):
                result = equity.collect_for_review(
                    "2026-10-28", history_path=target, now=clock,
                    client_factory=lambda: client,
                )
            self.assertEqual(client.reads, 1)
            self.assertEqual(result["daily_account_change_pct"], 4.0)
            self.assertEqual(result["status"], "PAPER_ACCOUNT_CHANGE_UNADJUSTED_CASH_FLOWS")
            self.assertFalse(result["full_portfolio_return_verified"])
            self.assertIsNone(result["daily_invested_capital_return_pct"])
            self.assertIsNone(result["since_inception_portfolio_return_pct"])
            self.assertIsNone(result["observed_window_max_drawdown_pct"])
            self.assertEqual(json.loads(target.read_text())["schema"], equity.SCHEMA)

            # Historical rerun reads only same-day saved evidence, never today's
            # different account value or a backdated current broker snapshot.
            old = equity.collect_for_review(
                "2026-10-28", history_path=target,
                now=datetime(2026, 10, 29, 16, 35, tzinfo=ET),
                client_factory=lambda: self.fail("Must not query broker for past date"),
            )
            self.assertEqual(old["daily_account_change_pct"], 4.0)

    def test_before_market_close_and_missing_credentials_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "evidence.json"
            client = FakeClient(FakeAccount())
            with patch.object(equity, "_calendar_close", return_value=datetime(2026, 10, 28, 16, tzinfo=ET)):
                early = equity.collect_for_review(
                    "2026-10-28", history_path=target,
                    now=datetime(2026, 10, 28, 15, 55, tzinfo=ET),
                    client_factory=lambda: client,
                )
            self.assertEqual(early["status"], "MARKET_SESSION_NOT_CLOSED")
            self.assertEqual(client.reads, 0)
            self.assertFalse(target.exists())

    def test_early_close_is_supported(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "history.json"
            with patch.object(equity, "_calendar_close", return_value=datetime(2026, 10, 28, 13, tzinfo=ET)):
                result = equity.collect_for_review(
                    "2026-10-28", history_path=target,
                    now=datetime(2026, 10, 28, 13, 6, tzinfo=ET),
                    client_factory=lambda: FakeClient(FakeAccount(100, 95)),
                )
            self.assertEqual(result["daily_account_change_pct"], -5.0)

    def test_sparse_curve_is_observed_window_not_inception(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "history.json"
            target.write_text(json.dumps({
                "schema": equity.SCHEMA,
                "account_key": "same",
                "days": {
                    "2026-10-26": {"prior_close_equity": 100, "observed_close_equity": 100},
                    "2026-10-28": {"prior_close_equity": 100, "observed_close_equity": 90},
                },
            }))
            result = equity.collect_for_review(
                "2026-10-28", history_path=target,
                now=datetime(2026, 10, 29, 16, tzinfo=ET),
            )
            self.assertEqual(result["observed_window_account_change_pct"], -10.0)
            self.assertEqual(result["observed_window_max_drawdown_pct"], 10.0)
            self.assertEqual(result["observed_session_count"], 2)
            self.assertIsNone(result["since_inception_portfolio_return_pct"])

    def test_account_switch_discards_old_curve(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "history.json"
            target.write_text(json.dumps({
                "schema": equity.SCHEMA,
                "account_key": "other_account_hash",
                "days": {"2026-10-27": {"prior_close_equity": 100, "observed_close_equity": 150}},
            }))
            with patch.object(equity, "_calendar_close", return_value=datetime(2026, 10, 28, 16, tzinfo=ET)):
                result = equity.collect_for_review(
                    "2026-10-28", history_path=target,
                    now=datetime(2026, 10, 28, 16, 30, tzinfo=ET),
                    client_factory=lambda: FakeClient(FakeAccount(100, 105)),
                )
            self.assertEqual(result["observed_session_count"], 1)
            self.assertIsNone(result["observed_window_account_change_pct"])
            self.assertNotIn("2026-10-27", json.loads(target.read_text())["days"])

    def test_invalid_account_values_are_not_converted_into_zero_return(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "history.json"
            with patch.object(equity, "_calendar_close", return_value=datetime(2026, 10, 28, 16, tzinfo=ET)):
                result = equity.collect_for_review(
                    "2026-10-28", history_path=target,
                    now=datetime(2026, 10, 28, 16, 30, tzinfo=ET),
                    client_factory=lambda: FakeClient(FakeAccount(0, float("nan"))),
                )
            self.assertEqual(result["status"], "PAPER_ACCOUNT_EQUITY_OR_ID_UNAVAILABLE")
            self.assertIsNone(result["daily_account_change_pct"])
            self.assertFalse(target.exists())

    def test_stale_session_cannot_steal_current_equity(self):
        with tempfile.TemporaryDirectory() as temp:
            client = FakeClient(FakeAccount())
            result = equity.collect_for_review(
                "2026-10-26", history_path=Path(temp) / "history.json",
                now=datetime(2026, 10, 28, 16, 30, tzinfo=ET),
                client_factory=lambda: client,
            )
            self.assertEqual(result["status"], "MISSING_DATED_BROKER_SNAPSHOT")
            self.assertEqual(client.reads, 0)


if __name__ == "__main__":
    unittest.main()
