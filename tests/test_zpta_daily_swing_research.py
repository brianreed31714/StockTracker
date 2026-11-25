"""Deterministic tests: day-t signal may enter no sooner than next-day open."""
import unittest
from datetime import date, timedelta
from analysis.zpta_daily_swing_research import research, daily_signals


def sample(n=160):
    first = date(2025, 1, 1)
    rows = []
    close = 1.0
    for i in range(n):
        old = close
        close *= (0.94 if i in (13, 14, 50, 51, 131) else 1.01)
        rows.append({"date": (first+timedelta(days=i)).isoformat(), "open": old,
                     "high": max(old, close)*1.02, "low": min(old, close)*.98,
                     "close": close, "volume": 100000})
    return rows


class ZptaDailySwingTests(unittest.TestCase):
    def test_require_historical_window(self):
        rows = sample()
        self.assertEqual(daily_signals(rows, 9), [])
        self.assertIn("one_day_decline_5pct", daily_signals(rows, 13))
        self.assertIn("two_down_days_total_5pct", daily_signals(rows, 14))

    def test_chronological_minimum(self):
        report = research(sample())
        self.assertEqual(report["validation_gate"]["status"], "READY_FOR_TRAIN_ONLY_SELECTION")
        self.assertGreater(report["signal_results"]["one_day_decline_5pct"]["1d"]["all"]["events"], 0)

    def test_short_history_has_no_complete_last_day_fill(self):
        report = research(sample(15))
        self.assertEqual(report["validation_gate"]["status"], "INSUFFICIENT_HISTORY")
        self.assertEqual(report["signal_results"]["two_down_days_total_5pct"]["1d"]["all"]["events"], 0)

    def test_zero_volume_rejects_all_entries(self):
        bars = sample()
        for bar in bars:
            bar["volume"] = 0
        report = research(bars)
        self.assertEqual(report["signal_results"]["all_eligible_sessions"]["1d"]["all"]["events"], 0)
        self.assertEqual(report["volume_filtered_signal_days"], len(bars) - 11)

    def test_cost_sensitivity_reduces_return(self):
        b = sample()
        free = research(b, one_way_cost=0)["signal_results"]["all_eligible_sessions"]["1d"]["all"]["mean_net_return_pct"]
        costly = research(b, one_way_cost=.03)["signal_results"]["all_eligible_sessions"]["1d"]["all"]["mean_net_return_pct"]
        self.assertGreater(free, costly)

    def test_holding_period_cross_boundary_is_purged(self):
        row = research(sample())["signal_results"]["all_eligible_sessions"]["5d"]
        self.assertLess(row["training"]["events"] + row["holdout"]["events"], row["all"]["events"])

    def test_invalid_cost(self):
        with self.assertRaises(ValueError):
            research(sample(), one_way_cost=-.01)


if __name__ == "__main__":
    unittest.main()
