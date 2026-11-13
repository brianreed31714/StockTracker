import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from analysis.zpta_down_streak_noon_study import build_rows, analyze

class DownStreakStudyTests(unittest.TestCase):
    def test_two_down_then_up_with_noon(self):
        tz = ZoneInfo("America/New_York")
        closes = [10.0, 9.0, 8.0, 8.8, 8.1]
        daily = [{"time": datetime(2026, 10, 5, 16, tzinfo=tz)+timedelta(days=i),
                  "close": c} for i,c in enumerate(closes)]
        hourly = [{"time": datetime(2026, 10, 8, 12, tzinfo=tz), "open": 8.4}]
        rows = build_rows(daily, hourly)
        target = next(r for r in rows if r["down_streak"] == 2)
        self.assertEqual(target["next_noon_price"], 8.4)
        self.assertAlmostEqual(target["next_eod_vs_signal_close_pct"], 10.0)
        self.assertEqual(analyze(rows)["down_2_exact"]["eod_vs_prior_close"]["up_count"], 1)

    def test_missing_noon_never_invented(self):
        tz = ZoneInfo("America/New_York")
        daily = [{"time": datetime(2026, 10, 5+i, 16, tzinfo=tz), "close": c}
                 for i,c in enumerate([10.0,9.0,8.0,9.0])]
        rows = build_rows(daily, [])
        self.assertIsNone(rows[-1]["next_noon_price"])
        self.assertIsNone(rows[-1]["next_noon_vs_signal_close_pct"])

if __name__ == "__main__":
    unittest.main()
