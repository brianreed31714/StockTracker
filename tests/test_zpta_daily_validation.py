"""Offline-only validation guardrails for ZPTA daily swing research."""
import unittest

from analysis.zpta_daily_validation import (
    select_nonoverlapping, event_bootstrap_ci, next_day_limit_eligibility,
)


class DailyValidationTests(unittest.TestCase):
    def test_overlap_purged(self):
        events = [
            {"entry_index": 2, "exit_index": 5, "return_pct": -10},
            {"entry_index": 3, "exit_index": 6, "return_pct": 40},
            {"entry_index": 6, "exit_index": 7, "return_pct": 2},
        ]
        result = select_nonoverlapping(events)
        self.assertEqual([e["entry_index"] for e in result], [2, 6])

    def test_same_day_reentry_not_independent(self):
        events = [
            {"entry_index": 1, "exit_index": 3},
            {"entry_index": 3, "exit_index": 5},
        ]
        self.assertEqual(len(select_nonoverlapping(events)), 1)

    def test_invalid_event_indices(self):
        with self.assertRaises(ValueError):
            select_nonoverlapping([{"entry_index": 5, "exit_index": 4}])

    def test_bootstrap_deterministic_and_wide_for_outlier(self):
        data = [-4.34, -5.04, -17.82, 30.88]
        a = event_bootstrap_ci(data, resamples=1000)
        b = event_bootstrap_ci(data, resamples=1000)
        self.assertEqual(a, b)
        self.assertEqual(a["events"], 4)
        self.assertLess(a["ci_pct"][0], 0)
        self.assertGreater(a["ci_pct"][1], 0)
        self.assertEqual(a["warning"], "LOW_SAMPLE_AND_IID_ASSUMPTION")

    def test_no_events(self):
        self.assertEqual(event_bootstrap_ci([])["warning"], "NO_EVENTS")

    def test_open_at_or_below_limit_is_not_verified_fill(self):
        r = next_day_limit_eligibility(1, .94, .92, discount_pct=.05)
        self.assertEqual(r["status"], "OPEN_PRINT_ELIGIBLE_FILL_UNVERIFIED")
        self.assertFalse(r["verified_fill"])
        self.assertIsNone(r["tradable_return_pct"])

    def test_low_touch_does_not_assert_fill(self):
        r = next_day_limit_eligibility(1, 1.03, .90, discount_pct=.05)
        self.assertEqual(r["status"], "LOW_TOUCHED_FILL_UNVERIFIED")
        self.assertFalse(r["verified_fill"])

    def test_no_limit_touch(self):
        r = next_day_limit_eligibility(1, 1.03, 1.00, discount_pct=.05)
        self.assertEqual(r["status"], "NOT_REACHED")

    def test_invalid_prices(self):
        with self.assertRaises(ValueError):
            next_day_limit_eligibility(1, 1, 1.1)


if __name__ == "__main__":
    unittest.main()
