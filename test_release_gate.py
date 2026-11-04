import unittest
from infrastructure.release_gate import evaluate_release


class ReleaseGateTests(unittest.TestCase):
    def test_missing_evidence_never_means_complete(self):
        result = evaluate_release(expected_commit="a" * 40, checks=[], host={})
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("REQUIRED_CI_NOT_OBSERVED", result["reasons"])
        self.assertIn("LOADED_CODE_UNVERIFIED", result["reasons"])

    def test_source_sync_is_not_loaded_runtime(self):
        result = evaluate_release(expected_commit="a" * 40,
            checks=[{"conclusion": "success"}],
            host={"git_head": "a" * 40, "source_code_synced": True, "processes_stable": True})
        self.assertTrue(result["source_synced"])
        self.assertFalse(result["loaded_runtime_verified"])

    def test_complete_claims_still_need_independent_review(self):
        result = evaluate_release(expected_commit="a" * 40,
            checks=[{"conclusion": "success"}],
            host={"git_head": "a" * 40, "source_code_synced": True,
                  "processes_stable": True, "in_memory_trader_digest_verified": True,
                  "loaded_code_sha256": "b" * 64, "loaded_dependencies_verified": True,
                  "loaded_dependencies_sha256": "c" * 64, "post_sync_eod_verified": True},
            notification={"provider_status": "API_ACCEPTED"})
        self.assertEqual(result["status"], "READY_FOR_INDEPENDENT_REVIEW")


if __name__ == "__main__":
    unittest.main()
