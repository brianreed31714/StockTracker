"""Deterministic tests for offline ZPTA dip research."""
import csv
import tempfile
import unittest
from pathlib import Path
from analysis.zpta_intraday_recovery import load_daily, summarize, chronological_gate


def bar(day, open_, high, low, close, volume=100000):
    return {"date": day, "open": open_, "high": high, "low": low, "close": close, "volume": volume}


class ZptaIntradayRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.bars = [bar("2026-10-01", 1, 1.1, 0.95, 1),
                     bar("2026-10-02", 0.90, 0.96, 0.70, 0.90),
                     bar("2026-10-05", 0.88, 0.98, 0.82, 0.96)]

    def test_intraday_recovery_is_not_a_fill(self):
        result = summarize(self.bars, thresholds=(0.10,), min_prior_day_dollar_volume=1000)
        event = result["thresholds"]["10%"]["events"][0]
        self.assertAlmostEqual(event["low_to_close_pct"], 28.5714, places=3)
        self.assertTrue(event["half_recovered_at_close"])
        self.assertFalse(event["fully_recovered_at_close"])
        self.assertAlmostEqual(event["next_open_to_close_gross_pct"], 9.0909, places=3)
        self.assertLess(event["next_day_net_3pct_each_side_pct"], event["next_open_to_close_gross_pct"])

    def test_censor_last_session(self):
        result = summarize(self.bars[:2], thresholds=(0.10,))
        self.assertEqual(result["thresholds"]["10%"]["summary"]["next_day_observable"], 0)
        self.assertEqual(result["thresholds"]["10%"]["summary"]["liquidity_proxy_eligible"], 0)

    def test_liquidity_filter_uses_signal_day_not_future_day(self):
        data = list(self.bars)
        data[1] = bar("2026-10-02", .90, .96, .70, .90, 10)
        data[2] = bar("2026-10-05", .88, .98, .82, .96, 100000000)
        result = summarize(data, thresholds=(0.10,))
        event = result["thresholds"]["10%"]["events"][0]
        self.assertFalse(event["liquidity_proxy_pass"])
        self.assertIsNone(event["next_day_net_1pct_each_side_pct"])

    def test_chronological_gate(self):
        self.assertEqual(chronological_gate(self.bars)["status"], "INSUFFICIENT_HISTORY")
        many = [bar(f"2025-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}", 1, 1.1, .9, 1) for i in range(150)]
        self.assertEqual(chronological_gate(many)["status"], "READY_FOR_TRAIN_ONLY_SELECTION")

    def test_invalid_and_duplicate_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.csv"
            with path.open("w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=self.bars[0].keys())
                writer.writeheader()
                writer.writerows(self.bars)
            self.assertEqual(len(load_daily(path)), 3)
            with path.open("a") as f:
                f.write("2026-10-02,0.90,0.96,0.70,0.90,100000\n")
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                load_daily(path)

    def test_reject_nonfinite_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.csv"
            path.write_text("date,open,high,low,close,volume\n2026-10-01,1,1,0.5,nan,100\n")
            with self.assertRaisesRegex(ValueError, "Nonfinite"):
                load_daily(path)


if __name__ == "__main__":
    unittest.main()
