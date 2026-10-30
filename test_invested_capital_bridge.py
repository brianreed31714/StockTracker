"""Ensure StockTracker's public report never fabricates portfolio/inception ROI."""
import unittest

from safe_summary_publish import summary_from


def fixture():
    return {
        "metrics": {
            "review_date": "2026-10-28", "paper_only": True,
            "coverage": {"db_path_exists": True, "dashboard_state_exists": True},
            "realized": {"rows": 1, "realized_pnl": 75, "wins": 1, "losses": 0},
            "orders": {"rows": 3, "buys": 2, "sells": 1},
            "decisions": {"rows": 1200}, "zpta_shadow": {}, "financial_leverage_shadow": {},
            "portfolio_performance": {
                "review_date": "2026-10-28", "source": "ALPACA_PAPER_ACCOUNT",
                "status": "PAPER_ACCOUNT_CHANGE_UNADJUSTED_CASH_FLOWS",
                "cash_flows_reconciled": False, "full_portfolio_return_verified": False,
                "daily_account_change_pct": 7.5,
            },
            "invested_capital": {
                "review_date": "2026-10-28",
                "source": "LOCAL_PAPER_FILLED_ORDERS_MOVING_AVERAGE",
                "status": "LOCAL_CLOSED_FILLS_RECONCILED_NOT_BROKER_ATTESTED",
                "daily_closed_invested_capital_return_pct": 14.285714,
                "daily_closed_cost_basis_usd": 525,
                "observed_fills_closed_invested_return_pct": 14.285714,
                "first_observed_fill_date": "2026-10-27",
                "peak_session_deployed_cost_usd": 2100,
                "broker_reconciled": True,
                "cash_flows_reconciled": True,
                "daily_invested_capital_return_status": "MODELED_PAPER_RETURN_ON_PEAK_DEPLOYED_COST",
                "daily_invested_capital_return_pct": 3.57142857,
                "private_order_ids": ["SECRET-123"],
                "ledger_end_quantities": {"NVDA": 15},
                "account_api_key": "SHOULD_NOT_APPEAR",
            },
        },
        "review": {
            "review_date": "2026-10-28", "data_quality": "GOOD",
            "review_source": "OPENAI",
        },
    }


class InvestedBridgeTests(unittest.TestCase):
    def test_broker_reconciled_daily_roi_is_not_called_inception(self):
        result = summary_from(fixture())
        measured = result["invested_capital"]
        self.assertEqual(measured["daily_portfolio_return_on_peak_deployed_capital_pct"], 3.5714)
        self.assertEqual(measured["daily_closed_lot_realized_return_pct"], 14.2857)
        self.assertIsNone(result["one_percent_goal"]["daily_portfolio_return_pct"])
        self.assertEqual(result["one_percent_goal"]["daily_invested_capital_return_pct"], 3.5714)
        self.assertEqual(result["one_percent_goal"]["return_basis"], "MODELED_PAPER_PEAK_DEPLOYED_FILLED_COST")
        self.assertTrue(result["one_percent_goal"]["daily_goal_met"])
        self.assertEqual(result["paper_account_observation"]["daily_account_change_pct"], 7.5)
        self.assertEqual(measured["classification"], "MODELED_PAPER")
        self.assertTrue(measured["daily_one_percent_invested_goal_met"])
        self.assertIsNone(measured["since_inception_invested_return_pct"])
        self.assertIsNone(measured["since_inception_invested_drawdown_pct"])
        rendered = str(result)
        for private in ("SECRET-123", "NVDA", "SHOULD_NOT_APPEAR"):
            self.assertNotIn(private, rendered)

    def test_account_gain_does_not_pass_invested_capital_goal(self):
        report = fixture()
        # Unadjusted paper-account change is +7.5%, but the reconciled
        # deployed-cost ROI is only +0.2%. Goal must be NOT MET.
        report["metrics"]["invested_capital"]["daily_invested_capital_return_pct"] = 0.2
        result = summary_from(report)
        self.assertEqual(result["paper_account_observation"]["daily_account_change_pct"], 7.5)
        self.assertEqual(result["one_percent_goal"]["daily_invested_capital_return_pct"], 0.2)
        self.assertFalse(result["one_percent_goal"]["daily_goal_met"])
        self.assertIsNone(result["one_percent_goal"]["daily_portfolio_return_pct"])

    def test_cashflow_or_broker_evidence_missing_disallows_portfolio_roi(self):
        for item in (
            {"broker_reconciled": False},
            {"cash_flows_reconciled": False},
            {"daily_invested_capital_return_status": "BROKER_MISSING"},
            {"review_date": "2026-10-27"},
            {"status": "LOCAL_REALIZED_AND_FILLS_RECONCILIATION_FAILED"},
        ):
            with self.subTest(item=item):
                report = fixture()
                report["metrics"]["invested_capital"].update(item)
                outcome = summary_from(report)
                self.assertIsNone(outcome["invested_capital"]["daily_portfolio_return_on_peak_deployed_capital_pct"])
                self.assertIsNone(outcome["one_percent_goal"]["daily_portfolio_return_pct"])
                self.assertIsNone(outcome["one_percent_goal"]["daily_invested_capital_return_pct"])
                self.assertIsNone(outcome["one_percent_goal"]["daily_goal_met"])

    def test_closed_lot_return_survives_broker_failure_but_is_not_portfolio(self):
        report = fixture()
        report["metrics"]["invested_capital"]["broker_reconciled"] = False
        result = summary_from(report)
        self.assertEqual(result["invested_capital"]["daily_closed_lot_realized_return_pct"], 14.2857)
        self.assertEqual(result["invested_capital"]["status"], "MODELED_LOCAL_CLOSED_LOTS_ONLY")
        self.assertIsNone(result["invested_capital"]["daily_portfolio_return_on_peak_deployed_capital_pct"])

    def test_observed_since_first_fill_not_inception_without_explicit_date(self):
        report = fixture()
        capital = report["metrics"]["invested_capital"]
        capital.update({
            "since_first_recorded_fill_portfolio_return_pct": 3.57142857,
            "since_first_recorded_fill_portfolio_drawdown_pct": 2.380952,
            "since_first_recorded_fill_sessions": 2,
            "inception_basis_status": "OBSERVED_FIRST_FILL_ONLY",
        })
        out = summary_from(report)["invested_capital"]
        self.assertEqual(out["since_first_observed_fill_portfolio_return_pct"], 3.5714)
        self.assertEqual(out["since_first_observed_fill_portfolio_drawdown_pct"], 2.381)
        self.assertIsNone(out["since_inception_invested_return_pct"])
        self.assertEqual(out["inception_evidence_status"], "OBSERVED_FIRST_FILL_NOT_PROVEN_INCEPTION")

    def test_true_inception_label_needs_confirmed_broker_history_and_start(self):
        report = fixture()
        capital = report["metrics"]["invested_capital"]
        capital.update({
            "since_first_recorded_fill_portfolio_return_pct": 3.57142857,
            "since_first_recorded_fill_portfolio_drawdown_pct": 0.0,
            "since_first_recorded_fill_sessions": 2,
            "inception_basis_status": "CONFIGURED_START_EQUALS_FIRST_FILL_WITH_BROKER_COVERAGE",
        })
        out = summary_from(report)["invested_capital"]
        self.assertEqual(out["since_inception_invested_return_pct"], 3.5714)
        self.assertEqual(out["since_inception_invested_drawdown_pct"], 0.0)
        capital["broker_reconciled"] = False
        out = summary_from(report)["invested_capital"]
        self.assertIsNone(out["since_inception_invested_return_pct"])

    def test_sanitized_broker_blocker_is_strictly_allowlisted(self):
        report = fixture()
        capital = report["metrics"]["invested_capital"]
        capital["broker_reconciled"] = False
        capital["broker_reconciliation_blocker"] = "BROKER_CASHFLOW_NOT_ZERO"
        out = summary_from(report)["invested_capital"]
        self.assertEqual(out["broker_reconciliation_blocker"], "BROKER_CASHFLOW_NOT_ZERO")
        self.assertIsNone(out["daily_portfolio_return_on_peak_deployed_capital_pct"])

        capital["broker_reconciliation_blocker"] = "PRIVATE_BROKER_TOKEN_ABC"
        out = summary_from(report)["invested_capital"]
        self.assertEqual(out["broker_reconciliation_blocker"], "UNVERIFIED")
        self.assertNotIn("PRIVATE_BROKER_TOKEN", str(out))

        capital["broker_reconciled"] = True
        capital["broker_reconciliation_blocker"] = "BROKER_CASHFLOW_NOT_ZERO"
        self.assertEqual(summary_from(report)["invested_capital"]["broker_reconciliation_blocker"], "NONE")

    def test_realized_dollars_cannot_become_percent(self):
        report = fixture()
        report["metrics"]["invested_capital"] = {}
        result = summary_from(report)
        self.assertEqual(result["daily"]["realized_pnl_usd"], 75.0)
        self.assertIsNone(result["invested_capital"]["daily_closed_lot_realized_return_pct"])
        self.assertIsNone(result["one_percent_goal"]["daily_goal_met"])


if __name__ == "__main__":
    unittest.main()
