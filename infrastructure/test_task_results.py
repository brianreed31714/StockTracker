"""Real scheduler results, including user's observed October 2026 error codes."""
from __future__ import annotations
import unittest
from infrastructure.runtime_inventory import classify_task_result, evaluate_task_registration


def task(name, code, *, state="Ready", script=None, trigger=None):
    supervisor=name.endswith(" Supervisor")
    return {
        "name":name, "state":state,"run_level":"Highest",
        "action_script":script or ("stocktracker_supervisor.py" if supervisor else "run_daily_model_review.bat"),
        "trigger_types":[trigger or ("LogonTrigger" if supervisor else "WeeklyTrigger")],
        "last_result":code,
    }


class TaskResultTests(unittest.TestCase):
    def test_running_supervisor_41301_is_not_failure(self):
        r=evaluate_task_registration(
            task("CryptoTracker Supervisor", 267009, state="Running",script="cryptotracker_supervisor.py"),
            {"name":"CryptoTracker Supervisor","script":"cryptotracker_supervisor.py","trigger":"at_logon"},
            "OBSERVED")
        self.assertEqual(r["last_result"]["state"], "RUNNING")
        self.assertFalse(r["warnings"])

    def test_old_stock_supervisor_abort_is_a_warning_not_process_outage(self):
        r=evaluate_task_registration(
            task("StockTracker Supervisor", 2147943467),
            {"name":"StockTracker Supervisor","script":"stocktracker_supervisor.py","trigger":"at_logon"},
            "OBSERVED")
        self.assertEqual(r["last_result"]["hex"], "0x8007042B")
        self.assertEqual(r["last_result"]["state"], "PROCESS_TERMINATED_UNEXPECTEDLY")
        self.assertTrue(r["warnings"])
        self.assertTrue(r["cautions"])
        self.assertEqual(r["supervisor_process_state"],"OBSERVED")
        self.assertFalse(r["startup_provenance_verified"])

    def test_daily_review_nonzero_exit_is_a_warning(self):
        r=evaluate_task_registration(
            task("StockTracker Daily Review", 1),
            {"name":"StockTracker Daily Review","script":"run_daily_model_review.bat","trigger":"weekday_13_30_local"})
        self.assertEqual(r["last_result"]["state"], "FAILED_OR_NONZERO_EXIT")
        self.assertTrue(r["warnings"])
        self.assertEqual(r["task_operational_status"], "NEEDS_ATTENTION")

    def test_successful_daily_review_is_not_warning(self):
        r=evaluate_task_registration(
            task("StockTracker Daily Review", 0),
            {"name":"StockTracker Daily Review","script":"run_daily_model_review.bat","trigger":"weekday_13_30_local"})
        self.assertEqual(r["warnings"], [])
        self.assertTrue(r["registration_consistent"])

    def test_unknown_last_result_does_not_claim_success(self):
        r=classify_task_result(None)
        self.assertEqual(r["state"], "UNKNOWN")

if __name__=="__main__":
    unittest.main()
