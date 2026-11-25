"""Chronological ZPTA holdout robustness tests, no market connections."""
import unittest
from datetime import date, timedelta
from analysis.zpta_daily_robustness import evaluate_holdout


def bars(n=160):
    first = date(2025,1,1)
    rows=[]
    px=1.
    for i in range(n):
        o=px
        px *= (.94 if i in (112,113,119,120,135) else 1.01)
        rows.append({"date": (first+timedelta(days=i)).isoformat(),
                     "open": o, "high": max(o,px)*1.02,
                     "low": min(o,px)*.98, "close": px, "volume": 100000})
    return rows


class DailyRobustnessTests(unittest.TestCase):
    def test_holdout_and_independence(self):
        r=evaluate_holdout(bars())
        self.assertEqual(r["holdout_sessions"], 48)
        b=r["results"]["all_eligible_sessions"]["3d"]
        self.assertLess(b["independent_events"], b["overlapping_candidates"])
        self.assertIsNotNone(b["max_full_allocation_drawdown_pct"])
        self.assertIn("gross_profit_to_loss_ratio", b)

    def test_missing_volume_cannot_generate_events(self):
        b=bars()
        for row in b:
            row["volume"]=0
        r=evaluate_holdout(b)
        self.assertEqual(r["results"]["all_eligible_sessions"]["3d"]["independent_events"],0)
        self.assertIsNone(r["results"]["all_eligible_sessions"]["3d"]["mean_net_pct"])

    def test_cost_sensitivity(self):
        b=bars()
        a=evaluate_holdout(b,one_way_cost=0)
        c=evaluate_holdout(b,one_way_cost=.03)
        self.assertGreater(a["results"]["all_eligible_sessions"]["3d"]["mean_net_pct"],
                           c["results"]["all_eligible_sessions"]["3d"]["mean_net_pct"])

    def test_holdout_has_no_future_outcome_at_end(self):
        r=evaluate_holdout(bars())
        one=r["results"]["all_eligible_sessions"]["1d"]["overlapping_candidates"]
        five=r["results"]["all_eligible_sessions"]["5d"]["overlapping_candidates"]
        self.assertGreater(one,five)

    def test_month_liquidity_control_is_observational(self):
        r = evaluate_holdout(bars())
        paired = r["results"]["two_down_days_total_5pct"]["3d"]["matched_month_liquidity"]
        self.assertLessEqual(paired["matched_pairs"],
                             r["results"]["two_down_days_total_5pct"]["3d"]["independent_events"])
        self.assertEqual(paired["warning"], "OBSERVATIONAL_MATCHES_NOT_INDEPENDENT_OR_CAUSAL")

    def test_bad_cost(self):
        with self.assertRaises(ValueError):
            evaluate_holdout(bars(),one_way_cost=-1)


if __name__=="__main__":
    unittest.main()
