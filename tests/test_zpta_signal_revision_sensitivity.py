"""Prevent silently promoting an RSI signal created by revised source bars."""
import unittest
from datetime import date, timedelta
from analysis.zpta_signal_revision_sensitivity import audit_previous_revision


def sample():
    rows = []
    d = date(2026, 10, 1)
    for i in range(11):
        close = .75 if i < 8 else (.72 if i == 8 else .73)
        rows.append({"date": (d+timedelta(days=i)).isoformat(),
                     "open": .75, "high": .80, "low": .69,
                     "close": close, "volume": 35982})
    return rows


def run(rows=None, **kwargs):
    b = sample() if rows is None else rows
    args = {"signal_date": b[-1]["date"],
            "frozen_previous_date": b[-2]["date"],
            "frozen_previous_close": .74,
            "frozen_previous_volume": 14491}
    args.update(kwargs)
    return audit_previous_revision(b, **args)


class RevisionSensitivityTests(unittest.TestCase):
    def test_one_cent_revision_flips_rsi3_signal(self):
        r = run()
        self.assertEqual(r["latest_rsi3"], 25)
        self.assertAlmostEqual(r["frozen_previous_close_rsi3"], 33.3333, places=3)
        self.assertIn("rsi3_at_most_25", r["latest_signal_flags"])
        self.assertNotIn("rsi3_at_most_25", r["frozen_previous_close_signal_flags"])
        self.assertEqual(r["source_quality_status"], "REVISION_CHANGED_SIGNAL_DO_NOT_PROMOTE")
        self.assertFalse(r["real_money_trading_allowed"])

    def test_same_previous_close_but_volume_revision_is_still_flagged(self):
        r = run(frozen_previous_close=.73)
        self.assertTrue(r["previous_bar_revision_detected"])
        self.assertFalse(r["signals_changed_by_previous_bar_revision"])
        self.assertEqual(r["source_quality_status"], "PREVIOUS_BAR_REVISION_REQUIRES_RECONCILIATION")

    def test_identical_previous_bar_does_not_verify_full_history(self):
        r = run(frozen_previous_close=.73, frozen_previous_volume=35982)
        self.assertFalse(r["previous_bar_revision_detected"])
        self.assertFalse(r["full_history_corporate_actions_verified"])
        self.assertFalse(r["real_money_trading_allowed"])

    def test_requires_immediately_previous_session(self):
        with self.assertRaisesRegex(ValueError, "immediately preceding"):
            run(frozen_previous_date="2026-09-01")

    def test_rejects_out_of_range_frozen_close(self):
        with self.assertRaisesRegex(ValueError, "outside"):
            run(frozen_previous_close=.99)

    def test_input_not_mutated(self):
        bars = sample()
        original = [dict(b) for b in bars]
        run(bars)
        self.assertEqual(bars, original)

    def test_duplicate_dates_rejected(self):
        bars = sample()
        bars[-1]["date"] = bars[-2]["date"]
        with self.assertRaisesRegex(ValueError, "unique"):
            run(bars)


if __name__ == "__main__":
    unittest.main()
