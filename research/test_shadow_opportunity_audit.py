"""Pure, no-network regression tests for shadow opportunity and exit research."""
import unittest
from datetime import datetime, timedelta, timezone

from research.shadow_opportunity_audit import analyze, shadow_exit


class ResearchAuditTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 10, 8, 14, 10, tzinfo=timezone.utc)

    def d(self, mins, price, symbol="NVDA"):
        return {
            "ts": (self.start + timedelta(minutes=mins)).isoformat(),
            "price": str(price),
            "symbol": symbol,
            "score": "71",
        }

    def gate(self, mins, symbol="NVDA", side="BUY", status="AWAITING_CONFIRMATION"):
        return {
            "ts": (self.start + timedelta(minutes=mins, seconds=3)).isoformat(),
            "symbol": symbol,
            "side": side,
            "score": "71.2",
            "gate_reason": status,
            "position_state": "NO_POSITION",
        }

    def test_forward_results_not_extrapolated_beyond_session(self):
        ds = [self.d(i, 100 + i * .02) for i in range(16)]
        events = [self.gate(2), self.gate(14)]
        output = analyze(ds, events)
        self.assertEqual(len(output["events"]), 2)
        self.assertIsNotNone(output["events"][0]["forward_gross_pct"]["5"])
        self.assertIsNone(output["events"][0]["forward_gross_pct"]["30"])
        self.assertIsNone(output["events"][1]["forward_gross_pct"]["5"])

    def test_episode_deduplication_independence_warning(self):
        ds = [self.d(i, 100) for i in range(75)]
        output = analyze(ds, [self.gate(1), self.gate(2), self.gate(20)])
        ids = [e["episode_id"] for e in output["events"]]
        self.assertEqual(ids[:2], [1, 1])
        self.assertNotEqual(ids[1], ids[2])
        self.assertIn("not independent", output["independence_warning"])

    def test_cost_assumptions_are_not_claimed_as_fills(self):
        ds = [self.d(i, 100 + i * 0.1) for i in range(70)]
        result = analyze(ds, [self.gate(0)], cost_bps=5)
        event = result["events"][0]
        self.assertAlmostEqual(event["forward_after_cost_pct"]["5"],
                               event["forward_gross_pct"]["5"] - 0.1, places=4)
        self.assertIsNone(result["portfolio_daily_return_pct"])
        self.assertEqual(result["atr_status"], "UNAVAILABLE_NO_OHLC_BARS")

    def test_no_shadow_exit_if_hour_missing(self):
        rows = [{"_ts": self.start + timedelta(minutes=i), "_price": 100.0}
                for i in range(59)]
        self.assertIsNone(shadow_exit(rows, self.start, 100.0))

    def test_stop_hit_in_shadow_does_not_modify_broker(self):
        rows = [{"_ts": self.start + timedelta(minutes=i), "_price": 98 if i >= 2 else 100}
                for i in range(61)]
        result = shadow_exit(rows, self.start, 100)
        self.assertEqual(result["exit"], "FIXED_STOP")
        self.assertLessEqual(result["gross_pct"], -2.0)


if __name__ == "__main__":
    unittest.main()
