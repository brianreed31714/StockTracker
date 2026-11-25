from datetime import date, timedelta
import unittest
from analysis.zpta_validation_bundle import independent_daily, volatility
from analysis.zpta_nonoverlap_selection_v1 import select_nonoverlapping as legacy_select
from analysis.zpta_independent_holdout import select_nonoverlapping


def bars():
    result = []
    start = date(2026, 1, 1)
    price = 1.
    for i in range(160):
        price *= .93 if i % 5 == 0 else 1.02
        result.append({"date": (start+timedelta(days=i)).isoformat(), "open": price,
                       "high": price*1.02, "low": price*.98, "close": price, "volume": 1000000})
    return result


class BundleTests(unittest.TestCase):
    def test_both_selection_interfaces_use_next_open(self):
        events = [{"signal_index": s, "exit_index": x} for s,x in [(2,5),(5,7),(6,9),(10,11)]]
        self.assertEqual(legacy_select(events), select_nonoverlapping(events))

    def test_volatility_does_not_read_future_prices(self):
        data = bars()
        before = volatility(data, 30)
        for b in data[31:]:
            b["close"] *= 100
        self.assertEqual(before, volatility(data, 30))

    def test_holdout_embargo_friction_and_no_promotion(self):
        one = independent_daily(bars(), .01)
        high = independent_daily(bars(), .025)
        self.assertFalse(one["eligible_for_promotion"])
        self.assertEqual(one["embargo_sessions"], 5)
        for name, cohort in one["results"].items():
            other = high["results"][name]
            self.assertEqual(cohort["signal_dates"], other["signal_dates"])
            if cohort["signals"]["n"]:
                self.assertLess(other["signals"]["mean_net_pct"], cohort["signals"]["mean_net_pct"])
            for d in cohort["signal_dates"]:
                index = next(i for i,b in enumerate(bars()) if b["date"] == d)
                if name.endswith("holdout"):
                    self.assertGreaterEqual(index, one["cutoff_index"]+5)
                else:
                    horizon = int(name.split("/")[1][:-1])
                    self.assertLess(index+horizon, one["cutoff_index"]-5)


if __name__ == "__main__":
    unittest.main()
