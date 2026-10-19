"""Pure timing tests: the running trader is NEVER imported or started."""
from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest
from zoneinfo import ZoneInfo

from post_close_review_policy import review_retry_decision

ROOT = Path(__file__).resolve().parent.parent
ET = ZoneInfo("America/New_York")
PT = ZoneInfo("America/Los_Angeles")


def load_timing_function(function_name, **bindings):
    source = (ROOT / "momentum_trader_v1_10_runtime_audit.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(
        n for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == function_name
    )
    scope = {"datetime": datetime, "timedelta": timedelta,
             "timezone": timezone, "ZoneInfo": ZoneInfo}
    scope.update(bindings)
    exec(compile(ast.Module(body=[node], type_ignores=[]), "<isolated timing>", "exec"), scope)
    return scope[function_name]


class TraderEodTimingTests(unittest.TestCase):
    def review_due(self, date_text, close_utc):
        now_et = datetime.fromisoformat(date_text + "T16:15:00").replace(tzinfo=ET)
        fn = load_timing_function(
            "post_close_review_due_target",
            POST_CLOSE_REVIEW_ENABLED=True,
            POST_CLOSE_REVIEW_DELAY_MINUTES=35,
            load_post_close_review_state=lambda: {},
            review_retry_decision=review_retry_decision,
            market_session_close_utc=lambda session_date: close_utc,
            MARKET_TZ=ET,
        )
        return fn(now_et)

    def test_summer_regular_close_135_pacific(self):
        target = self.review_due("2026-10-19", datetime(2026,10,19,20,tzinfo=timezone.utc))
        self.assertEqual(target.astimezone(PT).strftime("%Y-%m-%d %H:%M"), "2026-10-19 13:35")

    def test_winter_regular_close_135_pacific(self):
        target = self.review_due("2026-11-02", datetime(2026,11,2,21,tzinfo=timezone.utc))
        self.assertEqual(target.astimezone(PT).strftime("%Y-%m-%d %H:%M"), "2026-11-02 13:35")

    def test_early_close_does_not_start_before_135_pacific(self):
        target = self.review_due("2026-11-27", datetime(2026,11,27,18,tzinfo=timezone.utc))
        self.assertEqual(target.astimezone(PT).strftime("%Y-%m-%d %H:%M"), "2026-11-27 13:35")

    def test_no_trading_session_no_review(self):
        self.assertIsNone(self.review_due("2026-12-25", None))

    def test_performance_target_135_pacific_summer_and_winter(self):
        for date_text in ("2026-10-19", "2026-11-02"):
            fn = load_timing_function(
                "eod_due_target",
                PUSHOVER_STOCK_EOD_HOUR=16,
                PUSHOVER_STOCK_EOD_MINUTE=35,
                load_stock_eod_state=lambda: {},
            )
            before = datetime.fromisoformat(date_text + "T16:10").replace(tzinfo=ET)
            expected = datetime.fromisoformat(date_text + "T13:35").replace(tzinfo=PT)
            self.assertEqual(fn(before), expected.astimezone(ET))

    def test_never_send_performance_before_market_close(self):
        fn = load_timing_function(
            "eod_due_target",
            PUSHOVER_STOCK_EOD_HOUR=16,
            PUSHOVER_STOCK_EOD_MINUTE=35,
            load_stock_eod_state=lambda: {},
        )
        self.assertIsNone(fn(datetime(2026,10,19,15,59,tzinfo=ET)))

    def test_new_market_date_does_not_repeat_prior_sent_report(self):
        fn = load_timing_function(
            "eod_due_target",
            PUSHOVER_STOCK_EOD_HOUR=16,
            PUSHOVER_STOCK_EOD_MINUTE=35,
            load_stock_eod_state=lambda: {"last_sent_date": "2026-10-19"},
        )
        self.assertIsNone(fn(datetime(2026,10,19,16,35,tzinfo=ET)))


class HostSchedulingContractTests(unittest.TestCase):
    def test_source_configuration_matches_135_pacific(self):
        cfg = (ROOT / ".env.config").read_text(encoding="utf-8")
        self.assertIn("POST_CLOSE_REVIEW_DELAY_MINUTES=35", cfg)
        self.assertIn("PUSHOVER_STOCK_EOD_HOUR=16", cfg)
        self.assertIn("PUSHOVER_STOCK_EOD_MINUTE=35", cfg)

    def test_future_installer_uses_135_local(self):
        text = (ROOT / "install_stocktracker_tasks.ps1").read_text(encoding="utf-8")
        self.assertIn("-At 1:35PM", text)
        self.assertNotIn("-At 1:30PM", text)


if __name__ == "__main__":
    unittest.main()
