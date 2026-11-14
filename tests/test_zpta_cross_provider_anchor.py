"""Data-source discrepancies must be visible, not silently normalized."""
import unittest
from analysis.zpta_cross_provider_anchor import reconcile


def candidate(volume=67987):
    return {"symbol": "ZPTA", "as_of": "2026-10-26",
            "source": "Yahoo Finance chart public delayed research endpoint",
            "reference_close": .72, "reference_volume": volume}


def compare(snapshot=None, **kwargs):
    params = {"anchor_date": "2026-10-26", "anchor_close": .72,
              "anchor_volume": 279654, "anchor_source": "S&P Global Market Intelligence"}
    params.update(kwargs)
    return reconcile(candidate() if snapshot is None else snapshot, **params)


class CrossProviderAnchorTests(unittest.TestCase):
    def test_oct26_volume_discrepancy_is_material(self):
        r = compare()
        self.assertEqual(r["source_status"], "SOURCE_MISMATCH_DO_NOT_PROMOTE")
        self.assertAlmostEqual(r["volume_difference_pct"], 75.6889, delta=.01)
        self.assertAlmostEqual(r["candidate_turnover_proxy"], 48950.64)
        self.assertAlmostEqual(r["anchor_turnover_proxy"], 201350.88)
        self.assertFalse(r["real_money_trading_allowed"])

    def test_matching_anchor_is_not_full_history_verification(self):
        r = compare(candidate(279654))
        self.assertEqual(r["source_status"],
                         "SINGLE_DATE_ANCHOR_WITHIN_TOLERANCE_NOT_FULLY_VERIFIED")
        self.assertFalse(r["full_history_split_adjustment_verified"])

    def test_mismatched_date_fails(self):
        with self.assertRaisesRegex(ValueError, "date mismatch"):
            compare(anchor_date="2026-10-23")

    def test_same_source_fails(self):
        with self.assertRaisesRegex(ValueError, "distinct"):
            compare(anchor_source=candidate()["source"])

    def test_close_mismatch_fails(self):
        r = compare(candidate(279654), anchor_close=.75)
        self.assertEqual(r["source_status"], "SOURCE_MISMATCH_DO_NOT_PROMOTE")

    def test_invalid_anchor_fails(self):
        with self.assertRaises(ValueError):
            compare(anchor_volume=-1)


if __name__ == "__main__":
    unittest.main()
