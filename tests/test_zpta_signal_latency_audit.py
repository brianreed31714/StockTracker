"""Deterministic guards against interpreting delayed ZPTA labels as forecasts."""
import csv
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta
from analysis.zpta_signal_latency_audit import audit, parse_timestamp


class ZptaSignalLatencyAuditTests(unittest.TestCase):
    def run_rows(self, rows):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "predictions.csv"
            with path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=["bar_ts", "created_ts", "due_ts", "horizon_minutes", "model"])
                writer.writeheader()
                writer.writerows(rows)
            return audit([path])

    def test_delayed_horizons_and_independence(self):
        base = {"bar_ts": "2026-10-08T15:55:00+00:00", "created_ts": "2026-10-08T16:10:30+00:00"}
        rows = []
        for horizon in (5, 15, 60):
            for model in ("breakout", "pullback"):
                rows.append({**base, "horizon_minutes": horizon, "model": model,
                             "due_ts": (datetime.fromisoformat(base["bar_ts"]) + timedelta(minutes=horizon)).isoformat()})
        report = self.run_rows(rows)
        self.assertEqual(report["prediction_rows"], 6)
        self.assertEqual(report["distinct_bar_timestamps"], 1)
        self.assertEqual(report["distinct_bar_horizon_pairs"], 3)
        self.assertEqual(report["by_horizon"]["5"]["created_after_due"], 2)
        self.assertEqual(report["by_horizon"]["15"]["created_after_due"], 2)
        self.assertEqual(report["by_horizon"]["60"]["created_after_due"], 0)
        self.assertEqual(report["status"], "BLOCK_LIVE_VALIDATION")

    def test_fast_observation_is_timestamp_plausible_not_proof_of_fill(self):
        report = self.run_rows([{
            "bar_ts": "2026-10-08T15:55:00+00:00", "created_ts": "2026-10-08T15:55:02+00:00",
            "due_ts": "2026-10-08T16:00:00+00:00", "horizon_minutes": 5, "model": "x"}])
        self.assertEqual(report["status"], "TIMESTAMPS_PLAUSIBLE_ONLY")
        self.assertEqual(report["reference_price_stale"], 0)

    def test_stale_even_when_future_horizon(self):
        report = self.run_rows([{
            "bar_ts": "2026-10-08T15:55:00+00:00", "created_ts": "2026-10-08T16:10:00+00:00",
            "due_ts": "2026-10-08T16:55:00+00:00", "horizon_minutes": 60, "model": "x"}])
        self.assertEqual(report["created_after_due"], 0)
        self.assertEqual(report["reference_price_stale"], 1)
        self.assertEqual(report["status"], "BLOCK_LIVE_VALIDATION")

    def test_invalid_horizon_due_and_timestamps(self):
        row = {"bar_ts": "2026-10-08T15:55:00+00:00", "created_ts": "2026-10-08T15:55:02+00:00",
               "due_ts": "2026-10-08T16:02:00+00:00", "horizon_minutes": 5, "model": "x"}
        report = self.run_rows([row])
        self.assertIn("DUE_TIMESTAMP_INCONSISTENT", report["issues"])
        with self.assertRaises(ValueError):
            self.run_rows([{**row, "horizon_minutes": 0}])
        with self.assertRaises(ValueError):
            parse_timestamp("2026-10-08T15:55:00")

    def test_empty_and_missing_columns(self):
        self.assertEqual(audit([])["status"], "NO_DATA")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.csv"
            path.write_text("bar_ts\n2026-10-08T15:55:00+00:00\n")
            with self.assertRaisesRegex(ValueError, "Missing required"):
                audit([path])


if __name__ == "__main__":
    unittest.main()
