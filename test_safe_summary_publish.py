"""Tests deliberately contain secret-looking strings to catch accidental leakage."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import safe_summary_publish as bridge


def fixture(day="2026-10-19"):
    return {
        "metrics": {
            "paper_only": True,
            "review_date": day,
            "realized": {"rows": 2, "realized_pnl": 84.98, "wins": 2, "losses": 0,
                         "win_rate_pct": 100.0, "account_id": "PRIVATE_ACCOUNT_ID"},
            "orders": {"rows": 3, "buys": 1, "sells": 2,
                       "order_ids": ["BROKER_SECRET_ORDER_ID"]},
            "decisions": {"rows": 3150},
            "coverage": {"db_path_exists": True, "db_error": None,
                         "dashboard_state_exists": True},
            "zpta_shadow": {"resolved_predictions": 92, "shadow_trades": 0},
            "financial_leverage_shadow": {"signal_rows": 0},
            "dashboard_snapshot": {
                "positions": [{"symbol": "XOM", "qty": 9999}],
                "api_key": "PRIVATE_PROVIDER_TOKEN",
            },
        },
        "review": {"review_date": day, "data_quality": "LIMITED",
                   "review_source": "OPENAI",
                   "findings": ["Secret personal trade analysis: DO_NOT_EXPORT"],
                   "summary": "SECRET_REVIEW_TEXT"},
    }


class BridgeTests(unittest.TestCase):
    def test_explicit_allowlist_never_republishes_raw_data(self):
        report = fixture()
        current = {"review_date": "2026-10-19", "proposals": [
            {"proposal_id": "P-STOCK-20261019-01", "status": "APPROVED",
             "title": "PRIVATE_STRATEGY_TRADE_SECRET", "evidence": ["PRIVATE_LOG_LINE"]}
        ]}
        rendered = json.dumps(bridge.summary_from(report, current))
        for phrase in ("PRIVATE_ACCOUNT_ID", "BROKER_SECRET_ORDER_ID", "XOM",
                       "PRIVATE_PROVIDER_TOKEN", "DO_NOT_EXPORT", "SECRET_REVIEW_TEXT",
                       "PRIVATE_STRATEGY_TRADE_SECRET", "PRIVATE_LOG_LINE"):
            self.assertNotIn(phrase, rendered)
        self.assertEqual(json.loads(rendered)["daily"]["realized_pnl_usd"], 84.98)
        self.assertEqual(json.loads(rendered)["one_percent_goal"]["daily_portfolio_return_pct"], None)

    def test_reject_non_paper_or_date_mismatch(self):
        report = fixture()
        report["metrics"]["paper_only"] = False
        with self.assertRaises(ValueError):
            bridge.summary_from(report)
        report = fixture()
        report["review"]["review_date"] = "2026-10-18"
        with self.assertRaises(ValueError):
            bridge.summary_from(report)

    def test_fails_closed_on_corrupt_date(self):
        for date_text in ("2026-02-30", "../../local.env", "20261019"):
            report = fixture(day=date_text)
            with self.assertRaises(ValueError):
                bridge.summary_from(report)

    def test_local_export_is_summary_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            place = Path(tmp)
            runtime, repo = place / "runtime", place / "source"
            (runtime / "analysis/performance").mkdir(parents=True)
            (runtime / "analysis/performance/latest.json").write_text(json.dumps(fixture()))
            with patch.object(bridge, "ROOT", repo):
                result = bridge.publish(runtime, commit=False)
            self.assertEqual(result["review_date"], "2026-10-19")
            files = [p.relative_to(repo).as_posix() for p in repo.rglob("*.json")]
            self.assertEqual(sorted(files), [
                "analysis/performance/sanitized_daily/2026-10-19.json",
                "analysis/performance/sanitized_latest.json",
            ])
            self.assertNotIn("positions", (repo / "analysis/performance/sanitized_latest.json").read_text())

    def test_older_review_cannot_replace_newer(self):
        with tempfile.TemporaryDirectory() as tmp:
            place = Path(tmp)
            runtime, repo = place / "runtime", place / "source"
            (runtime / "analysis/performance").mkdir(parents=True)
            (repo / "analysis/performance").mkdir(parents=True)
            (runtime / "analysis/performance/latest.json").write_text(json.dumps(fixture("2026-10-18")))
            (repo / "analysis/performance/sanitized_latest.json").write_text(
                json.dumps({"schema": "stocktracker_sanitized_summary_v1", "review_date": "2026-10-19"}))
            with patch.object(bridge, "ROOT", repo):
                with self.assertRaises(RuntimeError):
                    bridge.publish(runtime, commit=False)

    def test_refuse_unrelated_worktree_changes(self):
        with patch.object(bridge, "git", side_effect=[
            "main", "", " M momentum_trader_v1_10_runtime_audit.py"
        ]):
            with self.assertRaises(RuntimeError):
                bridge.validate_git_safe("2026-10-19")

    def test_refuse_non_main_branch(self):
        with patch.object(bridge, "git", return_value="feature"):
            with self.assertRaises(RuntimeError):
                bridge.validate_git_safe("2026-10-19")


    def test_pushover_acceptance_requires_http_200_and_status_one(self):
        class Response:
            def __init__(self, code, payload):
                self.status_code = code
                self.payload = payload

            def json(self):
                if isinstance(self.payload, Exception):
                    raise self.payload
                return self.payload

        self.assertTrue(bridge.pushover_api_accepted(Response(200, {"status": 1})))
        for code, payload in [
            (400, {"status": 1}), (200, {"status": 0}),
            (200, {"status": "1"}), (200, {"status": True}), (200, []),
            (200, ValueError("invalid response")),
        ]:
            self.assertFalse(bridge.pushover_api_accepted(Response(code, payload)))

    def test_eod_pushover_receipt_is_dated_and_sanitized(self):
        report = fixture()
        report["metrics"]["eod_notification"] = {
            "review_date": "2026-10-19", "provider_status": "API_ACCEPTED",
            "device_delivery_verified": True,
            "token": "PRIVATE_PUSHOVER_TOKEN", "message_id": "PRIVATE_PUSH_ID",
        }
        result = bridge.summary_from(report)
        self.assertEqual(result["eod_notification"], {
            "provider_status": "API_ACCEPTED", "provider_accepted": True,
            "device_delivery_verified": False,
        })
        self.assertNotIn("PRIVATE_PUSHOVER_TOKEN", json.dumps(result))
        self.assertNotIn("PRIVATE_PUSH_ID", json.dumps(result))
        report["metrics"]["eod_notification"]["review_date"] = "2026-10-18"
        self.assertEqual(bridge.summary_from(report)["eod_notification"]["provider_status"], "UNVERIFIED")
        report["metrics"]["eod_notification"]["review_date"] = "2026-10-19"
        report["metrics"]["eod_notification"]["provider_status"] = "UNCONFIRMED"
        self.assertFalse(bridge.summary_from(report)["eod_notification"]["provider_accepted"])


if __name__ == "__main__":
    unittest.main()
