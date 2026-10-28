import unittest
from infrastructure.host_confirmation_reader import check_host_confirmation

HEAD = "a" * 40
NOW = "2026-10-27T20:00:00Z"


class HostConfirmationReaderTests(unittest.TestCase):
    def test_missing_report_fails_closed(self):
        result = check_host_confirmation({}, expected_commit=HEAD, observed_at_utc=NOW)
        self.assertEqual(result["status"], "UNVERIFIED")

    def test_source_only_is_not_deployment_verified(self):
        status = {"observed_at_utc": NOW, "git_head": HEAD,
                  "source_code_synced": True, "processes_stable": True}
        result = check_host_confirmation(status, expected_commit=HEAD, observed_at_utc=NOW)
        self.assertIn("LOADED_CODE_DIGEST_UNVERIFIED", result["reasons"])

    def test_stale_and_wrong_commit_rejected(self):
        status = {"observed_at_utc": "2026-10-26T20:00:00Z", "git_head": "b" * 40}
        result = check_host_confirmation(status, expected_commit=HEAD, observed_at_utc=NOW)
        self.assertIn("HOST_STATUS_STALE_OR_MISSING", result["reasons"])
        self.assertIn("EXPECTED_COMMIT_NOT_MATCHED", result["reasons"])

    def test_complete_structural_claims(self):
        status = {"observed_at_utc": NOW, "git_head": HEAD,
                  "source_code_synced": True, "processes_stable": True,
                  "loaded_code_sha256": "c" * 64,
                  "in_memory_trader_digest_verified": True,
                  "loaded_dependencies_sha256": "d" * 64,
                  "loaded_dependencies_verified": True,
                  "post_sync_eod_verified": True, "process_recovery_verified": True}
        self.assertEqual(check_host_confirmation(status, expected_commit=HEAD,
                         observed_at_utc=NOW)["status"], "CLAIMS_COMPLETE_UNCORROBORATED")


if __name__ == "__main__":
    unittest.main()
