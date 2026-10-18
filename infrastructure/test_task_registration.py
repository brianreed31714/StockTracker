"""Tests that Windows task 'Ready' is not a stopped-supervisor assertion."""
from __future__ import annotations

import unittest

from infrastructure.runtime_inventory import evaluate_task_registration


SUPERVISOR = {
    "name": "StockTracker Supervisor",
    "script": "stocktracker_supervisor.py",
    "trigger": "at_logon",
}
REVIEW = {
    "name": "StockTracker Daily Review",
    "script": "run_daily_model_review.bat",
    "trigger": "weekday_13_30_local",
}


def task(state="Ready", script="stocktracker_supervisor.py", kind="LogonTrigger", run_level="Highest"):
    return {
        "name": "StockTracker Supervisor",
        "state": state,
        "action_script": script,
        "trigger_types": [kind],
        "run_level": run_level,
    }


class TaskRegistrationTests(unittest.TestCase):
    def test_supervisor_ready_and_process_observed_is_a_caution_not_outage(self):
        result = evaluate_task_registration(task(), SUPERVISOR, "OBSERVED")
        self.assertEqual(result["warnings"], [])
        self.assertTrue(result["registration_consistent"])
        self.assertTrue(result["cautions"])
        self.assertFalse(result["startup_provenance_verified"])

    def test_supervisor_running_and_process_observed_has_no_caution(self):
        result = evaluate_task_registration(task(state="Running"), SUPERVISOR, "OBSERVED")
        self.assertFalse(result["warnings"])
        self.assertFalse(result["cautions"])
        self.assertFalse(result["startup_provenance_verified"])

    def test_ready_without_identified_process_is_warning(self):
        result = evaluate_task_registration(task(), SUPERVISOR, "UNKNOWN")
        self.assertFalse(result["registration_consistent"])
        self.assertTrue(result["warnings"])

    def test_disabled_task_is_warning_even_if_process_running(self):
        result = evaluate_task_registration(task(state="Disabled"), SUPERVISOR, "OBSERVED")
        self.assertFalse(result["registration_consistent"])

    def test_wrong_action_is_warning(self):
        result = evaluate_task_registration(task(script="different_supervisor.py"), SUPERVISOR, "OBSERVED")
        self.assertFalse(result["registration_consistent"])
        self.assertTrue(any("different script" in x for x in result["warnings"]))

    def test_missing_action_never_passes_registration(self):
        result = evaluate_task_registration(task(script=""), SUPERVISOR, "OBSERVED")
        self.assertFalse(result["registration_consistent"])

    def test_wrong_trigger_is_warning(self):
        result = evaluate_task_registration(task(kind="DailyTrigger"), SUPERVISOR, "OBSERVED")
        self.assertFalse(result["registration_consistent"])

    def test_wrong_privileges_is_warning(self):
        result = evaluate_task_registration(task(run_level="Limited"), SUPERVISOR, "OBSERVED")
        self.assertFalse(result["registration_consistent"])

    def test_weekday_review_ready_is_normal(self):
        data = task(state="Ready", script="run_daily_model_review.bat", kind="WeeklyTrigger")
        data["name"] = "StockTracker Daily Review"
        result = evaluate_task_registration(data, REVIEW)
        self.assertTrue(result["registration_consistent"])
        self.assertFalse(result["warnings"])
        self.assertFalse(result["cautions"])

    def test_weekday_review_wrong_trigger_is_warning(self):
        data = task(state="Ready", script="run_daily_model_review.bat", kind="LogonTrigger")
        data["name"] = "StockTracker Daily Review"
        result = evaluate_task_registration(data, REVIEW)
        self.assertFalse(result["registration_consistent"])


if __name__ == "__main__":
    unittest.main()
