"""Deterministic boundary tests for independent ZPTA holdout research."""
import unittest
from analysis.zpta_independent_holdout import select_nonoverlapping


def event(signal, exit_):
    return {"signal_index": signal, "exit_index": exit_, "net_return_pct": 0.0}


class EmbargoTests(unittest.TestCase):
    def test_training_boundary_exclusion(self):
        events = [event(10, 11), event(15, 17), event(16, 19)]
        result = select_nonoverlapping(events, split_index=20,
                                       segment="training", embargo_sessions=3)
        self.assertEqual([x["signal_index"] for x in result], [10])

    def test_holdout_boundary_exclusion(self):
        events = [event(20, 21), event(22, 23), event(23, 24), event(25, 26)]
        result = select_nonoverlapping(events, split_index=20,
                                       segment="holdout", embargo_sessions=3)
        self.assertEqual([x["signal_index"] for x in result], [23, 25])

    def test_zero_embargo_retains_previous_behavior(self):
        events = [event(18, 19), event(20, 21)]
        self.assertEqual(len(select_nonoverlapping(events, split_index=20,
                                                   segment="training")), 1)
        self.assertEqual(len(select_nonoverlapping(events, split_index=20,
                                                   segment="holdout")), 1)

    def test_negative_embargo_rejected(self):
        with self.assertRaises(ValueError):
            select_nonoverlapping([], embargo_sessions=-1)


if __name__ == "__main__":
    unittest.main()
