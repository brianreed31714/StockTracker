import unittest
from analysis.zpta_independent_holdout import select_nonoverlapping, evaluate


def event(s, x, r=1):
    return {"signal_index": s, "exit_index": x, "net_return_pct": r}


class IndependentHoldoutTests(unittest.TestCase):
    def test_no_overlapping_positions(self):
        result = select_nonoverlapping([event(3, 6), event(2, 5), event(5, 7), event(6, 9)])
        self.assertEqual([e["signal_index"] for e in result], [2, 6])

    def test_embargo_training_and_holdout(self):
        events = [event(6, 9), event(8, 11), event(10, 12)]
        self.assertEqual([e["signal_index"] for e in select_nonoverlapping(
            events, split_index=10, segment="training")], [6])
        self.assertEqual([e["signal_index"] for e in select_nonoverlapping(
            events, split_index=10, segment="holdout")], [10])

    def test_empty_and_small_sample_uncertainty(self):
        self.assertIsNone(evaluate([])["mean_net_pct"])
        self.assertIsNone(evaluate([event(0, 1)])["mean_ci95_pct"])

    def test_compounding_and_drawdown_not_same_as_mean(self):
        result = evaluate([event(0, 1, 10), event(2, 3, -10)])
        self.assertAlmostEqual(result["compounded_trade_return_pct"], -1)
        self.assertAlmostEqual(result["max_trade_sequence_drawdown_pct"], 10)

    def test_bad_event_rejected(self):
        with self.assertRaises(ValueError):
            select_nonoverlapping([event(5, 5)])


if __name__ == "__main__":
    unittest.main()
