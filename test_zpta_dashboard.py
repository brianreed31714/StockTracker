"""ZPTA dashboard correctness: Eastern dates, real sample counts, diagnostics, no trading."""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from zpta_dashboard_support import (
    all_time_resolved_forecasts,
    daily_resolved_forecasts,
    explain_zpta_status,
    latest_observation,
    market_timestamp_label,
    resolution_market_date,
)


def populate(path: Path):
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE zpta_predictions (
                id TEXT, model TEXT, horizon_minutes INTEGER,
                resolved_ts TEXT, correct INTEGER, forward_return REAL
            );
            CREATE TABLE zpta_observations (
                ts TEXT, provider TEXT, price REAL
            );
        """)
        db.executemany(
            "INSERT INTO zpta_predictions VALUES (?,?,?,?,?,?)",
            [
                ("1", "breakout_continuation", 5, "2026-10-16T01:00:00+00:00", 0, -0.001),
                ("2", "breakout_continuation", 5, "2026-10-16T20:00:00+00:00", 1, 0.008),
                ("3", "breakout_continuation", 5, "2026-10-16T20:05:00+00:00", 0, -0.002),
                ("4", "breakout_continuation", 15, "2026-10-16T20:05:00+00:00", 1, 0.02),
                ("5", "exhaustion_exit", 5, "2026-10-16T20:08:00+00:00", 1, 0.003),
                ("6", "exhaustion_exit", 5, None, None, None),
            ],
        )
        db.execute(
            "INSERT INTO zpta_observations VALUES (?,?,?)",
            ("2026-10-16T20:10:00+00:00", "yahoo_delayed", 0.52),
        )


class ResolutionDateTests(unittest.TestCase):
    def test_resolution_date_is_et_not_utc(self):
        self.assertEqual(resolution_market_date("2026-10-16T01:00:00Z"), "2026-10-15")
        self.assertEqual(resolution_market_date("2026-10-16T20:00:00+00:00"), "2026-10-16")

    def test_daylight_saving_transition(self):
        self.assertEqual(resolution_market_date("2026-03-08T06:59:00Z"), "2026-03-08")
        self.assertEqual(resolution_market_date("2026-03-08T07:01:00Z"), "2026-03-08")
        self.assertEqual(market_timestamp_label("2026-10-16T20:10:00Z"), "2026-10-16 04:10 PM EDT")

    def test_no_timestamps_are_not_fabricated(self):
        self.assertIsNone(resolution_market_date(None))
        self.assertIsNone(resolution_market_date("invalid"))


class SqlAggregationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "zpta.sqlite3"
        populate(self.path)

    def test_daily_grid_contains_eastern_market_date(self):
        rows = daily_resolved_forecasts(self.path)
        self.assertTrue(all("market_date" in row for row in rows))
        self.assertEqual(rows[0]["market_date"], "2026-10-16")
        self.assertEqual(rows[-1]["market_date"], "2026-10-15")

    def test_correct_sample_counts_and_percentages(self):
        rows = daily_resolved_forecasts(self.path)
        by_key = {(r["market_date"],r["model"],r["horizon_minutes"]):r for r in rows}
        target = by_key[("2026-10-16","breakout_continuation",5)]
        self.assertEqual(target["samples"], 2)
        self.assertEqual(target["accuracy_pct"], 50.0)
        self.assertEqual(target["avg_return_pct"], 0.3)
        older = by_key[("2026-10-15","breakout_continuation",5)]
        self.assertEqual(older["samples"], 1)
        self.assertEqual(older["accuracy_pct"], 0.0)

    def test_all_time_summary_is_retained(self):
        summary = all_time_resolved_forecasts(self.path)
        target = next(r for r in summary
                      if r["model"] == "breakout_continuation" and r["horizon_minutes"] == 5)
        self.assertEqual(target["samples"], 3)
        self.assertEqual(target["accuracy_pct"], 33.3)

    def test_last_quote_is_explicitly_historical(self):
        observation = latest_observation(self.path)
        self.assertEqual(observation["provider"], "yahoo_delayed")
        self.assertEqual(observation["price"], 0.52)

    def test_limit_applied_after_daily_aggregation(self):
        rows = daily_resolved_forecasts(self.path,max_groups=1)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["samples"],2)

    def test_read_only_missing_database_creates_nothing(self):
        missing = self.path.with_name("never_created.sqlite")
        self.assertEqual(daily_resolved_forecasts(missing), [])
        self.assertEqual(all_time_resolved_forecasts(missing), [])
        self.assertIsNone(latest_observation(missing))
        self.assertFalse(missing.exists())

    def test_group_limit_must_be_in_safe_range(self):
        with self.assertRaises(ValueError):
            daily_resolved_forecasts(self.path,max_groups=0)


class StatusTests(unittest.TestCase):
    def test_auth_failure_has_useful_safe_explanation(self):
        s = {"status":"ERROR","error":"401 invalid token secret=SUPERSECRET"}
        message=explain_zpta_status(s)
        self.assertIn("authentication",message.lower())
        self.assertNotIn("SUPERSECRET",message)

    def test_no_new_bars_near_market_open(self):
        text=explain_zpta_status({"status":"ERROR","error":
            "Need at least 10 current-session trade bars; received 2"})
        self.assertIn("10",text)

    def test_provider_rate_limit_explanation(self):
        text=explain_zpta_status({"status":"ERROR","error":"HTTPError 429 Too Many Requests"})
        self.assertIn("rate-limited",text)

    def test_unknown_error_does_not_print_exception(self):
        text=explain_zpta_status({"status":"ERROR","error":"secret or user path: C:/users/brian/.env"})
        self.assertNotIn("brian",text)
        self.assertNotIn(".env",text)

    def test_valid_status_does_not_warn(self):
        for status in ("OK","NO_NEW_BAR","DISABLED"):
            self.assertIsNone(explain_zpta_status({"status":status}))


class DashboardContractTests(unittest.TestCase):
    def test_uses_dated_forecasts_and_keeps_lifetime(self):
        source=(Path(__file__).resolve().parent/"momentum_dashboard_v1_3_agentic.py").read_text(encoding="utf-8")
        compile(source,"dashboard","exec")
        self.assertIn('daily_resolved_forecasts(DB)', source)
        self.assertIn('all_time_resolved_forecasts(DB)', source)
        self.assertIn('Daily detail (ET)', source)
        self.assertIn('explain_zpta_status(z)', source)
        self.assertIn('READ ONLY', source)


if __name__ == "__main__":
    unittest.main()
