"""Fail-closed privacy bridge for read-only PAPER account percentage."""
import unittest

from safe_summary_publish import summary_from


def sample():
    return {
        "metrics": {
            "review_date": "2026-10-28",
            "paper_only": True,
            "coverage": {"db_path_exists": True, "dashboard_state_exists": True},
            "realized": {"rows": 2, "realized_pnl": 84.91, "wins": 2, "losses": 0},
            "orders": {"rows": 6, "buys": 4, "sells": 2},
            "decisions": {"rows": 3250},
            "zpta_shadow": {},
            "financial_leverage_shadow": {},
            "portfolio_performance": {
                "review_date": "2026-10-28",
                "source": "ALPACA_PAPER_ACCOUNT",
                "status": "PAPER_ACCOUNT_CHANGE_UNADJUSTED_CASH_FLOWS",
                "daily_account_change_pct": 0.123456,
                "daily_invested_capital_return_pct": None,
                "since_inception_portfolio_return_pct": None,
                "observed_window_account_change_pct": 1.5,
                "observed_window_max_drawdown_pct": 3.2,
                "observed_session_count": 5,
                "cash_flows_reconciled": False,
                "full_portfolio_return_verified": False,
                "broker_account_id": "PRIVATE-NOT-FOR-GITHUB",
                "position_details": [{"symbol": "NVDA", "qty": 99}],
            },
        },
        "review": {"review_date": "2026-10-28", "data_quality": "GOOD",
                   "review_source": "OPENAI"},
    }


class PaperEquityBridgeTests(unittest.TestCase):
    def test_dated_account_change_survives_without_leaking_private_equity(self):
        result = summary_from(sample())
        account = result["paper_account_observation"]
        self.assertEqual(account["daily_account_change_pct"], 0.1235)
        self.assertEqual(account["observed_window_max_drawdown_pct"], 3.2)
        self.assertIsNone(account["invested_capital_daily_return_pct"])
        self.assertIsNone(result["one_percent_goal"]["daily_portfolio_return_pct"])
        self.assertNotIn("broker_account_id", str(result))
        self.assertNotIn("PRIVATE-NOT-FOR-GITHUB", str(result))
        self.assertNotIn("NVDA", str(result))

    def test_mismatched_or_unverified_date_is_not_published_as_portfolio_return(self):
        for change in (
            {"review_date": "2026-10-27"},
            {"source": "LIVE_ACCOUNT"},
            {"status": "MISSING_DATED_BROKER_SNAPSHOT"},
            {"cash_flows_reconciled": True},
            {"full_portfolio_return_verified": True},
        ):
            report = sample()
            report["metrics"]["portfolio_performance"].update(change)
            result = summary_from(report)
            self.assertIsNone(result["paper_account_observation"]["daily_account_change_pct"])
            self.assertEqual(result["paper_account_observation"]["status"], "MISSING")

    def test_realized_usd_never_transforms_to_fake_percent(self):
        report = sample()
        del report["metrics"]["portfolio_performance"]
        result = summary_from(report)
        self.assertEqual(result["daily"]["realized_pnl_usd"], 84.91)
        self.assertIsNone(result["paper_account_observation"]["daily_account_change_pct"])
        self.assertIsNone(result["one_percent_goal"]["daily_portfolio_return_pct"])


if __name__ == "__main__":
    unittest.main()
