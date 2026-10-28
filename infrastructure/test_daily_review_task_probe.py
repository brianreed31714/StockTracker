import json
import subprocess
import unittest
from datetime import datetime, timedelta, timezone
from infrastructure.daily_review_task_probe import inspect_daily_review_task

NOW = datetime(2026, 10, 28, 11, 0, tzinfo=timezone.utc)


def response(value, returncode=0):
    return subprocess.CompletedProcess([], returncode, stdout=json.dumps(value), stderr="")


class TaskProbeTests(unittest.TestCase):
    def test_named_task_is_observation_not_eod_receipt(self):
        value = {"state": "Ready", "last_run_utc": "2026-10-28T01:05:00+00:00", "last_result": 0}
        seen = []
        def runner(command, **kwargs):
            seen.append((command, kwargs))
            return response(value)
        result = inspect_daily_review_task(clock=NOW, runner=runner)
        self.assertEqual(result["status"], "TASK_NAME_OBSERVED")
        self.assertEqual(result["last_task_result"], 0)
        self.assertFalse(result["eod_delivery_verified"])
        self.assertIn("StockTracker Daily Review", seen[0][0][-1])
        self.assertNotIn("Start-ScheduledTask", seen[0][0][-1])

    def test_no_last_run_is_not_successful_eod(self):
        result = inspect_daily_review_task(clock=NOW, runner=lambda *a, **k: response(
            {"state": "Ready", "last_run_utc": None, "last_result": 267011}))
        self.assertEqual(result["status"], "TASK_NAME_OBSERVED")
        self.assertIsNone(result["last_run_utc"])

    def test_future_time_rejected(self):
        future = (NOW + timedelta(seconds=1)).isoformat()
        result = inspect_daily_review_task(clock=NOW, runner=lambda *a, **k: response(
            {"state": "Ready", "last_run_utc": future, "last_result": 0}))
        self.assertEqual(result["status"], "UNVERIFIED")

    def test_missing_task_or_failure_fails_closed(self):
        result = inspect_daily_review_task(clock=NOW, runner=lambda *a, **k: response({}, 1))
        self.assertEqual(result["status"], "UNVERIFIED")

    def test_untrusted_output_fails_closed(self):
        for payload in (
            {"state": "Ready", "last_run_utc": None, "last_result": True},
            {"state": "Ready", "last_run_utc": "not-a-time", "last_result": 0},
            {"state": "EOD_DELIVERED", "last_run_utc": None, "last_result": 0},
            {"state": "Ready", "last_run_utc": None, "last_result": "0"},
        ):
            with self.subTest(payload=payload):
                result = inspect_daily_review_task(clock=NOW, runner=lambda *a, **k: response(payload))
                self.assertEqual(result["status"], "UNVERIFIED")


if __name__ == "__main__":
    unittest.main()
