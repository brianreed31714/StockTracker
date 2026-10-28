"""Offline tests for the read-only StockTracker evidence freshness auditor.

Run: python -m unittest discover -s tests -p 'test_report_freshness_audit.py'
No network, broker, environment files, or runtime process required.
"""
import json
import tempfile
import unittest
from pathlib import Path

from analysis.report_freshness_audit import audit


class ReportFreshnessAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.report_dir = self.root / "analysis" / "performance"
        self.evidence_dir = self.root / "analysis" / "evidence" / "2026-10-13"
        self.report_dir.mkdir(parents=True)
        self.evidence_dir.mkdir(parents=True)
        self.write_report()
        self.write_manifest()
        (self.evidence_dir / "realized.csv").write_text(
            "id,pnl,symbol,ts\n1,12.50,XOM,2026-10-13T18:00:00Z\n",
            encoding="utf-8",
        )

    def write_report(self, date="2026-10-13", paper_only=True, symbols=None):
        if symbols is None:
            symbols = ["XOM", "NBIS"]
        (self.report_dir / "latest.json").write_text(
            json.dumps({"metrics": {
                "review_date": date, "paper_only": paper_only,
                "config": {"trade_symbols": symbols},
            }}),
            encoding="utf-8",
        )

    def write_manifest(self, status="PASS", issues=None, empty_tables=None):
        (self.evidence_dir / "manifest.json").write_text(
            json.dumps({
                "review_date": "2026-10-13",
                "integrity_analysis": {
                    "status": status,
                    "issues": issues or [],
                    "empty_tables": empty_tables or [],
                },
            }),
            encoding="utf-8",
        )

    def test_valid_report_has_observed_realized_not_account_return(self):
        result = audit(self.root, "2026-10-13")
        self.assertEqual(result["published_realized_pnl_usd_observed_only"], "12.50")
        self.assertEqual(result["published_realized_row_count"], 1)
        self.assertFalse(result["account_equity_return_available"])
        self.assertFalse(result["account_max_drawdown_available"])
        self.assertEqual(result["status"], "WARN")

    def test_stale_report_is_failure(self):
        self.write_report(date="2026-10-08")
        result = audit(self.root, "2026-10-13")
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("STALE_REPORT" in x for x in result["errors"]))

    def test_absent_realized_evidence_is_missing_not_zero(self):
        (self.evidence_dir / "realized.csv").unlink()
        result = audit(self.root, "2026-10-13")
        self.assertIsNone(result["published_realized_pnl_usd_observed_only"])
        self.assertEqual(result["realized_evidence_status"], "MISSING")
        self.assertIn("MISSING_REALIZED_EVIDENCE_NOT_ZERO_PNL", result["warnings"])
        self.assertEqual(result["published_realized_row_count"], 0)

    def test_missing_report_is_failure(self):
        (self.report_dir / "latest.json").unlink()
        result = audit(self.root, "2026-10-13")
        self.assertIn("MISSING_LATEST_REPORT", result["errors"])

    def test_paper_only_invariant_is_required(self):
        self.write_report(paper_only=False)
        result = audit(self.root, "2026-10-13")
        self.assertIn("PAPER_ONLY_NOT_CONFIRMED", result["errors"])

    def test_manifest_integrity_failure_propagates(self):
        self.write_manifest(status="FAIL", issues=["ORPHAN_ORDER"])
        result = audit(self.root, "2026-10-13")
        self.assertIn("EVIDENCE_INTEGRITY_NOT_PASS", result["errors"])

    def test_missing_nbis_and_empty_research_table_are_warnings(self):
        self.write_report(symbols=["XOM"])
        self.write_manifest(empty_tables=["premarket_intelligence"])
        result = audit(self.root, "2026-10-13")
        self.assertIn("NBIS_NOT_IN_REPORTED_RUNTIME_UNIVERSE", result["warnings"])
        self.assertIn("EMPTY_RESEARCH_TABLE: premarket_intelligence", result["warnings"])

    def test_duplicate_realized_rows_are_not_double_counted(self):
        with (self.evidence_dir / "realized.csv").open("a", encoding="utf-8") as file:
            file.write("1,12.50,XOM,2026-10-13T18:00:00Z\n")
        result = audit(self.root, "2026-10-13")
        self.assertEqual(result["published_realized_pnl_usd_observed_only"], "12.50")
        self.assertEqual(result["published_realized_row_count"], 1)
        self.assertTrue(any("DUPLICATE_REALIZED_ROW" in x for x in result["warnings"]))


    def test_conflicting_duplicate_realized_rows_fail_closed(self):
        with (self.evidence_dir / "realized.csv").open("a", encoding="utf-8") as file:
            file.write("1,999.00,XOM,2026-10-13T18:00:00Z\n")
        result = audit(self.root, "2026-10-13")
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["realized_evidence_status"], "INVALID")
        self.assertIsNone(result["published_realized_pnl_usd_observed_only"])
        self.assertTrue(any("CONFLICTING_DUPLICATE_REALIZED_ROW" in e for e in result["errors"]))

    def test_missing_realized_identity_fails_closed(self):
        with (self.evidence_dir / "realized.csv").open("a", encoding="utf-8") as file:
            file.write(",9.00,XOM,2026-10-13T19:00:00Z\n")
        result = audit(self.root, "2026-10-13")
        self.assertEqual(result["realized_evidence_status"], "INVALID")
        self.assertIsNone(result["published_realized_pnl_usd_observed_only"])

    def test_noncanonical_report_date_is_rejected(self):
        self.write_report(date="../2026-10-13")
        result = audit(self.root, "2026-10-13")
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("INVALID_LATEST_REPORT" in e for e in result["errors"]))

    def test_future_session_realized_file_is_excluded(self):
        future_dir = self.root / "analysis" / "evidence" / "2026-10-14"
        future_dir.mkdir(parents=True)
        (future_dir / "realized.csv").write_text(
            "id,pnl,symbol,ts\n2,9000.00,XOM,2026-10-14T18:00:00Z\n",
            encoding="utf-8",
        )
        result = audit(self.root, "2026-10-13")
        self.assertEqual(result["published_realized_pnl_usd_observed_only"], "12.50")
        self.assertEqual(result["published_realized_row_count"], 1)
        self.assertEqual(result["published_sessions_with_realized_file"], ["2026-10-13"])
        self.assertIn("FUTURE_REALIZED_EVIDENCE_EXCLUDED: 2026-10-14", result["warnings"])

    def test_nonfinite_realized_pnl_is_invalid_not_reported(self):
        with (self.evidence_dir / "realized.csv").open("a", encoding="utf-8") as file:
            file.write("2,NaN,XOM,2026-10-13T19:00:00Z\n")
        result = audit(self.root, "2026-10-13")
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["realized_evidence_status"], "INVALID")
        self.assertIsNone(result["published_realized_pnl_usd_observed_only"])
        self.assertTrue(any("INVALID_REALIZED_CSV" in error for error in result["errors"]))


    def test_future_trade_timestamp_inside_older_folder_fails_closed(self):
        # A file labeled Oct 13 must not contain an Oct 14 New York trade.
        (self.evidence_dir / "realized.csv").write_text(
            "id,pnl,symbol,ts\n1,9999.00,XOM,2026-10-14T18:00:00Z\n",
            encoding="utf-8",
        )
        result = audit(self.root, "2026-10-13")
        self.assertEqual(result["realized_evidence_status"], "INVALID")
        self.assertIsNone(result["published_realized_pnl_usd_observed_only"])
        self.assertTrue(any("realized trade session mismatch" in x for x in result["errors"]))

    def test_utc_midnight_belongs_to_prior_new_york_session(self):
        (self.evidence_dir / "realized.csv").write_text(
            "id,pnl,symbol,ts\n1,12.50,XOM,2026-10-14T00:15:00Z\n",
            encoding="utf-8",
        )
        result = audit(self.root, "2026-10-13")
        self.assertEqual(result["realized_evidence_status"], "OBSERVED_ONLY")
        self.assertEqual(result["published_realized_pnl_usd_observed_only"], "12.50")

    def test_timezone_naive_trade_timestamp_is_unverified(self):
        (self.evidence_dir / "realized.csv").write_text(
            "id,pnl,symbol,ts\n1,12.50,XOM,2026-10-13T18:00:00\n",
            encoding="utf-8",
        )
        result = audit(self.root, "2026-10-13")
        self.assertEqual(result["realized_evidence_status"], "INVALID")
        self.assertIsNone(result["published_realized_pnl_usd_observed_only"])


    def test_same_trade_id_with_changed_timestamp_fails_closed(self):
        # A duplicated trade cannot become two realized gains by changing ts.
        with (self.evidence_dir / "realized.csv").open("a", encoding="utf-8") as file:
            file.write("1,12.50,XOM,2026-10-13T18:01:00Z\n")
        result = audit(self.root, "2026-10-13")
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["realized_evidence_status"], "INVALID")
        self.assertIsNone(result["published_realized_pnl_usd_observed_only"])
        self.assertTrue(any("CONFLICTING_DUPLICATE_REALIZED_ROW" in e for e in result["errors"]))

    def test_equivalent_utc_timestamp_is_deduplicated(self):
        with (self.evidence_dir / "realized.csv").open("a", encoding="utf-8") as file:
            file.write("1,12.50,XOM,2026-10-13T18:00:00+00:00\n")
        result = audit(self.root, "2026-10-13")
        self.assertEqual(result["published_realized_pnl_usd_observed_only"], "12.50")
        self.assertEqual(result["published_realized_row_count"], 1)
        self.assertEqual(result["realized_evidence_status"], "OBSERVED_ONLY")

    def test_session_scoped_trade_ids_can_repeat_across_days(self):
        prior = self.root / "analysis" / "evidence" / "2026-10-12"
        prior.mkdir(parents=True)
        (prior / "realized.csv").write_text(
            "id,pnl,symbol,ts\n1,3.00,XOM,2026-10-12T18:00:00Z\n",
            encoding="utf-8",
        )
        result = audit(self.root, "2026-10-13")
        self.assertEqual(result["published_realized_pnl_usd_observed_only"], "15.50")
        self.assertEqual(result["published_realized_row_count"], 2)


if __name__ == "__main__":
    unittest.main()
