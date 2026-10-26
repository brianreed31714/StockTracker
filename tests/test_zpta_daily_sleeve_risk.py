"""Offline portfolio-risk tests; synthetic prices, no broker connections."""
import unittest
from datetime import date, timedelta

from analysis.zpta_daily_sleeve_risk import (
    loss_budget_stress, simulate_shadow_sleeve,
)


def synthetic(n=160):
    start = date(2025, 1, 1)
    bars = []
    price = 1.0
    for i in range(n):
        opened = price
        price *= (0.94 if i in (115, 118, 135) else 1.006)
        bars.append({
            "date": (start + timedelta(days=i)).isoformat(),
            "open": opened,
            "high": max(opened, price) * 1.02,
            "low": min(opened, price) * 0.97,
            "close": price,
            "volume": 200000,
        })
    return bars


class DailySleeveRiskTests(unittest.TestCase):
    def test_stress_worst_prior_observation_exceeds_daily_budget(self):
        r = loss_budget_stress(-49.17)
        self.assertAlmostEqual(r["net_sleeve_pnl_dollars"], -73.755)
        self.assertAlmostEqual(r["net_sleeve_return_pct"], -7.3755)
        self.assertEqual(r["daily_loss_budget_dollars"], 30)
        self.assertTrue(r["loss_exceeds_one_day_budget"])

    def test_smaller_position_reduces_dollar_risk(self):
        large = loss_budget_stress(-40)
        small = loss_budget_stress(-40, max_position_dollars=50)
        self.assertGreater(small["net_sleeve_pnl_dollars"], large["net_sleeve_pnl_dollars"])

    def test_next_open_only_and_nonoverlap(self):
        bars = synthetic()
        r = simulate_shadow_sleeve(bars, "all_eligible_sessions", horizon=3)
        trades = r["trades"]
        self.assertGreater(len(trades), 0)
        for t in trades:
            signal_i = next(i for i, bar in enumerate(bars)
                            if bar["date"] == t["signal_date"])
            self.assertEqual(t["entry_index"], signal_i + 1)
            self.assertEqual(t["exit_index"], signal_i + 3)
            self.assertLessEqual(t["invested_dollars"], 150)
        for left, right in zip(trades, trades[1:]):
            self.assertLess(left["exit_index"], right["entry_index"])
        self.assertFalse(r["eligible_for_live_trading"])

    def test_zero_volume_fail_closed(self):
        bars = synthetic()
        for bar in bars:
            bar["volume"] = 0
        r = simulate_shadow_sleeve(bars, "one_day_decline_5pct")
        self.assertEqual(r["nonoverlapping_trades"], 0)
        self.assertEqual(r["ending_equity"], 1000)

    def test_cost_sensitivity(self):
        bars = synthetic()
        free = simulate_shadow_sleeve(bars, "all_eligible_sessions", one_way_cost=0)
        costly = simulate_shadow_sleeve(bars, "all_eligible_sessions", one_way_cost=.03)
        self.assertGreater(free["ending_equity"], costly["ending_equity"])

    def test_risk_gaps_do_not_pretend_stop_fills(self):
        bars = synthetic()
        bars[125]["low"] = bars[125]["open"] * .30
        r = simulate_shadow_sleeve(bars, "all_eligible_sessions", horizon=3)
        self.assertIn("INTRADAY_LOW_MARK_NOT_STOP_EXECUTION_OR_KNOWN_SEQUENCE", r["warnings"])
        self.assertGreaterEqual(r["intraday_low_proxy_daily_budget_breaches"], 1)

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            loss_budget_stress(-101)
        with self.assertRaises(ValueError):
            simulate_shadow_sleeve(synthetic(), "unregistered_signal")
        with self.assertRaises(ValueError):
            simulate_shadow_sleeve(synthetic(), "all_eligible_sessions", horizon=2)


    def test_start_signal_date_excludes_earlier_market_regime(self):
        r = simulate_shadow_sleeve(
            synthetic(), "all_eligible_sessions", horizon=5,
            start_signal_date="2025-05-15")
        self.assertGreater(r["nonoverlapping_trades"], 0)
        self.assertTrue(all(t["signal_date"] >= "2025-05-15" for t in r["trades"]))
        self.assertEqual(r["start_signal_date"], "2025-05-15")

    def test_future_market_start_fails_closed_to_no_trades(self):
        r = simulate_shadow_sleeve(
            synthetic(), "all_eligible_sessions", horizon=5,
            start_signal_date="2027-01-01")
        self.assertEqual(r["nonoverlapping_trades"], 0)
        self.assertEqual(r["ending_equity"], 1000)

if __name__ == "__main__":
    unittest.main()
