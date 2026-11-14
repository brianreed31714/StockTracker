"""Deterministic acceptance tests for independent ZPTA daily swing trade selection."""
import unittest
from analysis.zpta_nonoverlap_selection_v1 import embargoed_split, select_nonoverlapping


def event(signal, exit_):
    return {"signal_index": signal, "exit_index": exit_, "net_return_pct": 1.0}


class SelectionTests(unittest.TestCase):
    def test_overlap_and_same_day_conflict(self):
        source = [event(4, 9), event(1, 5), event(6, 7), event(5, 6), event(8, 10)]
        self.assertEqual([(e["signal_index"], e["exit_index"]) for e in select_nonoverlapping(source)],
                         [(1, 5), (6, 7), (8, 10)])

    def test_order_independence_and_no_mutation(self):
        source = [event(4, 6), event(1, 3), event(2, 5)]
        before = [dict(e) for e in source]
        self.assertEqual(select_nonoverlapping(source), select_nonoverlapping(list(reversed(source))))
        self.assertEqual(source, before)

    def test_boundary_purge(self):
        result = embargoed_split([event(2, 4), event(5, 9), event(8, 11),
                                 event(10, 12), event(11, 13), event(14, 16)], 10)
        self.assertEqual([e["signal_index"] for e in result["training"]], [2, 5])
        self.assertEqual([e["signal_index"] for e in result["holdout"]], [10, 14])

    def test_invalid_events(self):
        with self.assertRaises(ValueError):
            select_nonoverlapping([event(3, 3)])
        with self.assertRaises(ValueError):
            embargoed_split([], -1)


if __name__ == "__main__":
    unittest.main()
