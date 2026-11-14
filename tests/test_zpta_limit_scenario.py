import unittest
from analysis.zpta_limit_scenario import classify_buy_limit


class LimitScenarioTests(unittest.TestCase):
    def test_open_below_limit_is_not_verified_execution(self):
        r = classify_buy_limit(prior_close=1, next_open=.95, next_low=.90, next_high=1.05)
        self.assertEqual(r["classification"], "open_marketable_unverified")
        self.assertFalse(r["fill_verified"])

    def test_touch_not_guaranteed_fill(self):
        r = classify_buy_limit(prior_close=1, next_open=1.02, next_low=.97, next_high=1.04)
        self.assertEqual(r["classification"], "intraday_touch_fill_unknown")
        self.assertFalse(r["fill_verified"])

    def test_missed_limit(self):
        r = classify_buy_limit(prior_close=1, next_open=1.02, next_low=.99, next_high=1.04)
        self.assertEqual(r["classification"], "not_touched")

    def test_bad_ohlc_rejected(self):
        with self.assertRaises(ValueError):
            classify_buy_limit(prior_close=1, next_open=1.05, next_low=1.06, next_high=1.10)
