"""Independent daily OHLCV reconciliation tests; no network or broker."""
import unittest
from analysis.zpta_daily_ohlcv_reconcile import reconcile


A = "2026-10-29T23:00:00Z"
B = "2026-10-29T23:05:00Z"


def bar(d="2026-10-26", o=.75, h=.75, l=.631, c=.72, v=279654):
    return {"date": d, "open": o, "high": h, "low": l, "close": c, "volume": v}


def check(left, right):
    return reconcile(left, right, candidate_source="S&P published table",
                     reference_source="EODData published table",
                     candidate_retrieved_utc=A, reference_retrieved_utc=B)


class DailyOhlcvReconcileTests(unittest.TestCase):
    def test_oct26_open_mismatch_even_when_close_and_volume_match(self):
        result = check([bar()], [bar(o=.69)])
        self.assertEqual(result["mismatch_dates"], ["2026-10-26"])
        self.assertEqual(result["rows"][0]["mismatched_fields"], ["open"])
        self.assertAlmostEqual(result["rows"][0]["difference_pct"]["open"], 8.695652, places=5)
        self.assertFalse(result["eligible_for_model_promotion"])

    def test_oct23_open_mismatch(self):
        result = check([bar(d="2026-10-23", o=.80, h=.80, l=.736, c=.75, v=19451)],
                       [bar(d="2026-10-23", o=.736, h=.80, l=.736, c=.75, v=19451)])
        self.assertEqual(result["rows"][0]["mismatched_fields"], ["open"])

    def test_matching_sample_not_verified_full_history(self):
        result = check([bar()], [bar()])
        self.assertEqual(result["status"], "SAMPLE_MATCH_NOT_FULL_HISTORY_VERIFIED")
        self.assertFalse(result["full_history_corporate_action_adjustments_verified"])
        self.assertFalse(result["executable_bid_ask_size_verified"])

    def test_volume_mismatch_detected(self):
        result = check([bar(v=67987)], [bar()])
        self.assertIn("volume", result["rows"][0]["mismatched_fields"])

    def test_missing_date_fails_closed(self):
        result = check([bar()], [bar(), bar(d="2026-10-27", o=.72, h=.75, l=.69, c=.73, v=35982)])
        self.assertEqual(result["missing_dates"], ["2026-10-27"])
        self.assertFalse(result["eligible_for_model_promotion"])

    def test_zero_volume_not_tradable(self):
        result = check([bar(v=0)], [bar(v=0)])
        self.assertEqual(result["status"], "ZERO_VOLUME_REQUIRES_EXCLUSION")

    def test_unsorted_duplicate_and_invalid_ohlc_rejected(self):
        with self.assertRaises(ValueError):
            check([bar(), bar()], [bar()])
        with self.assertRaises(ValueError):
            check([bar(h=.70)], [bar()])

    def test_unaware_timestamp_rejected(self):
        with self.assertRaises(ValueError):
            reconcile([bar()], [bar()], candidate_source="A", reference_source="B",
                      candidate_retrieved_utc="2026-10-29T23:00:00",
                      reference_retrieved_utc=B)

    def test_same_source_rejected(self):
        with self.assertRaises(ValueError):
            reconcile([bar()], [bar()], candidate_source="same", reference_source="same",
                      candidate_retrieved_utc=A, reference_retrieved_utc=B)

    def test_tolerance_cannot_hide_open_field(self):
        with self.assertRaises(ValueError):
            reconcile([bar()], [bar()], candidate_source="A", reference_source="B",
                      candidate_retrieved_utc=A, reference_retrieved_utc=B,
                      tolerance_pct={"close": .5})


if __name__ == "__main__":
    unittest.main()
