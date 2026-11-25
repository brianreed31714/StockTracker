"""Offline tests for next-session limit scenarios; no broker connection."""
import copy
import unittest
from datetime import date, timedelta

from analysis.zpta_next_session_limit_audit import (
    audit, classify_next_session, limit_price,
)


def bars(n=20):
    first = date(2026, 1, 1)
    data = [
        {"date": (first + timedelta(days=i)).isoformat(),
         "open": 1.0, "high": 1.1, "low": .9, "close": 1.0,
         "volume": 100000}
        for i in range(n)
    ]
    data[12].update(close=.90, low=.88)
    if n > 13:
        data[13].update(open=.85, high=1.0, low=.80, close=.95)
    return data


class LimitAuditTests(unittest.TestCase):
    def test_limit_uses_only_completed_signal_day(self):
        a = bars()
        price = limit_price(a, 12)
        b = copy.deepcopy(a)
        b[13].update(open=.01, low=.001, close=.01)
        self.assertEqual(price, limit_price(b, 12))
        self.assertAlmostEqual(price, .873)

    def test_classification_never_assumes_intraday_touch_filled(self):
        self.assertEqual(classify_next_session(.8, None), "PENDING_NEXT_SESSION")
        self.assertEqual(classify_next_session(.8, {"open": .9, "low": .7}),
                         "INTRADAY_TOUCH_NO_FILL_ASSUMED")
        self.assertEqual(classify_next_session(.8, {"open": .7, "low": .6}),
                         "OPEN_PRINT_ELIGIBLE_UNVERIFIED")
        self.assertEqual(classify_next_session(.8, {"open": .9, "low": .85}),
                         "LIMIT_NOT_REACHED")

    def test_last_signal_is_pending_not_hindsight_fill(self):
        a = bars(13)
        report = audit(a)
        self.assertEqual(report["candidate_count"], 1)
        self.assertEqual(report["candidates"][0]["status"], "PENDING_NEXT_SESSION")
        self.assertIsNone(report["candidates"][0]["horizon_outcomes"]["1d"])

    def test_open_print_scenario_is_unverified(self):
        report = audit(bars())
        event = report["candidates"][0]
        self.assertEqual(event["status"], "OPEN_PRINT_ELIGIBLE_UNVERIFIED")
        self.assertFalse(event["broker_fill_verified"])
        self.assertIsNotNone(event["horizon_outcomes"]["5d"])
        self.assertFalse(event["horizon_outcomes"]["5d"]["broker_fill_verified"])
        self.assertFalse(report["real_money_trading_allowed"])

    def test_intraday_touch_is_not_counted_as_fill(self):
        a = bars()
        a[13]["open"] = .95
        report = audit(a)
        self.assertEqual(report["candidates"][0]["status"],
                         "INTRADAY_TOUCH_NO_FILL_ASSUMED")
        self.assertTrue(all(v is None for v in report["candidates"][0]["horizon_outcomes"].values()))
        self.assertEqual(report["nonoverlapping_summary"]["5d"]["nonoverlapping_open_print_scenarios"], 0)

    def test_cost_sensitivity(self):
        a = bars()
        cheap = audit(a, one_way_cost=0)["candidates"][0]["horizon_outcomes"]["3d"]["limit_open_print_scenario_net_pct"]
        expensive = audit(a, one_way_cost=.03)["candidates"][0]["horizon_outcomes"]["3d"]["limit_open_print_scenario_net_pct"]
        self.assertGreater(cheap, expensive)

    def test_no_future_five_day_outcome(self):
        report = audit(bars(14))
        self.assertIsNotNone(report["candidates"][0]["horizon_outcomes"]["1d"])
        self.assertIsNone(report["candidates"][0]["horizon_outcomes"]["3d"])
        self.assertIsNone(report["candidates"][0]["horizon_outcomes"]["5d"])

    def test_reject_bad_inputs(self):
        with self.assertRaises(ValueError):
            audit(bars(), signal_name="optimized_after_seeing_future")
        with self.assertRaises(ValueError):
            audit(bars(), one_way_cost=-.01)
        with self.assertRaises(ValueError):
            audit(bars(), discount=1)
        a = bars()
        a[13]["date"] = a[12]["date"]
        with self.assertRaises(ValueError):
            audit(a)

    def test_missing_volume_rejects_candidate(self):
        a = bars()
        a[12]["volume"] = 0
        self.assertEqual(audit(a)["candidate_count"], 0)

    def test_no_fills_claimed_even_when_scenario_positive(self):
        report = audit(bars())
        self.assertFalse(report["executable_quotes_verified"])
        self.assertFalse(report["data_adjustment_verified"])
        self.assertEqual(report["nonoverlapping_summary"]["5d"]["nonoverlapping_open_print_scenarios"], 1)


if __name__ == "__main__":
    unittest.main()
