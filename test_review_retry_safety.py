"""Regression tests for StockTracker reporting failures. No Alpaca/OpenAI calls.

The paper trader function is evaluated from its AST in an isolated namespace;
the live module is NEVER imported (it would create broker clients).
"""
from __future__ import annotations

import ast
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import unittest

from post_close_review_policy import (
    review_retry_decision,
    MAX_ATTEMPTS_PER_SESSION,
    FAILED_RETRY_COOLDOWN_MINUTES,
)
import post_close_review_guard as guard


ROOT = Path(__file__).resolve().parent
DATE = "2026-10-16"
BASE = datetime(2026, 10, 16, 22, 0, tzinfo=timezone.utc)


class RetryPolicyTests(unittest.TestCase):
    def test_new_session_has_fresh_budget(self):
        s = {"review_date": "2026-10-15", "status": "FAILED", "attempts": 93}
        self.assertEqual(review_retry_decision(s, DATE, now=BASE)["action"], "RUN")

    def test_completed_review_never_replayed(self):
        s = {"review_date": DATE, "status": "COMPLETED", "attempts": 1}
        self.assertEqual(review_retry_decision(s, DATE, now=BASE)["reason"], "COMPLETED")

    def test_running_review_never_started_twice(self):
        s = {"review_date": DATE, "status": "RUNNING", "attempts": 1,
             "started_at": (BASE-timedelta(minutes=4)).isoformat()}
        self.assertEqual(review_retry_decision(s, DATE, now=BASE)["reason"], "ALREADY_RUNNING")

    def test_missing_running_time_fails_closed(self):
        s = {"review_date": DATE, "status": "RUNNING", "attempts": 1}
        self.assertEqual(review_retry_decision(s, DATE, now=BASE)["reason"], "RUNNING_TIME_UNVERIFIED")

    def test_stale_running_retries_only_with_remaining_budget(self):
        s = {"review_date": DATE, "status": "RUNNING", "attempts": 2,
             "started_at": (BASE-timedelta(minutes=60)).isoformat()}
        self.assertEqual(review_retry_decision(s, DATE, now=BASE)["action"], "RUN")
        s["attempts"] = 3
        self.assertEqual(review_retry_decision(s, DATE, now=BASE)["reason"], "RETRY_LIMIT")

    def test_93_attempts_is_blocked_and_never_incremented(self):
        s = {"review_date": DATE, "status": "FAILED", "attempts": 93,
             "finished_at": (BASE-timedelta(minutes=20)).isoformat()}
        self.assertEqual(review_retry_decision(s, DATE, now=BASE)["reason"], "RETRY_LIMIT")

    def test_failure_cooldown_and_next_retry(self):
        finished = BASE-timedelta(minutes=5)
        s = {"review_date": DATE, "status": "FAILED", "attempts": 1,
             "finished_at": finished.isoformat()}
        result = review_retry_decision(s, DATE, now=BASE)
        self.assertEqual(result["action"], "WAIT")
        self.assertEqual(result["next_attempt_utc"], finished+timedelta(minutes=FAILED_RETRY_COOLDOWN_MINUTES))
        self.assertEqual(review_retry_decision(s, DATE, now=BASE+timedelta(minutes=11))["action"], "RUN")

    def test_missing_failed_time_fails_closed(self):
        s = {"review_date": DATE, "status": "FAILED", "attempts": 1}
        self.assertEqual(review_retry_decision(s, DATE, now=BASE)["reason"], "FAILED_TIME_UNVERIFIED")

    def test_invalid_attempts_fails_closed(self):
        s = {"review_date": DATE, "status": "FAILED", "attempts": "INVALID"}
        self.assertEqual(review_retry_decision(s, DATE, now=BASE)["reason"], "INVALID_ATTEMPT_COUNT")


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        patches = [
            patch.object(guard, "STATE_PATH", root/"review.json"),
            patch.object(guard, "LEGACY_STATE_PATH", root/"review_mirror.json"),
            patch.object(guard, "LOCK_PATH", root/"runtime"/"post_close_review_guard.lock"),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def state(self):
        return json.loads(guard.STATE_PATH.read_text(encoding="utf-8"))

    def test_93_prior_attempts_never_mutated(self):
        guard.STATE_PATH.write_text(json.dumps({
            "review_date": DATE, "status": "FAILED", "attempts": 93,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }))
        self.assertEqual(guard.begin(DATE), 21)
        self.assertEqual(self.state()["attempts"], 93)

    def test_three_attempts_then_exhaustion(self):
        for count in range(1, MAX_ATTEMPTS_PER_SESSION+1):
            self.assertEqual(guard.begin(DATE), 0)
            self.assertEqual(self.state()["attempts"], count)
            self.assertEqual(guard.finish(DATE, "FAILED", "pipeline failed", "bundle"), 0)
            self.assertEqual(self.state()["failure_stage"], "bundle")
            # Simulate elapsed cooldown without sleeping or running models.
            s = self.state()
            s["finished_at"] = (datetime.now(timezone.utc)-timedelta(minutes=20)).isoformat()
            guard.STATE_PATH.write_text(json.dumps(s))
        self.assertEqual(guard.begin(DATE), 21)
        self.assertEqual(self.state()["attempts"], MAX_ATTEMPTS_PER_SESSION)

    def test_guard_respects_cooldown(self):
        self.assertEqual(guard.begin(DATE), 0)
        self.assertEqual(guard.finish(DATE, "FAILED", "pipeline failed", "model_review"), 0)
        self.assertEqual(guard.begin(DATE), 22)
        self.assertEqual(self.state()["attempts"], 1)

    def test_finish_does_not_falsely_complete_without_running_lock(self):
        self.assertEqual(guard.finish(DATE, "COMPLETED"), 1)
        self.assertFalse(guard.STATE_PATH.exists())

    def test_completed_lock_is_never_replayed(self):
        self.assertEqual(guard.begin(DATE), 0)
        self.assertEqual(guard.finish(DATE, "COMPLETED"), 0)
        self.assertEqual(guard.begin(DATE), 20)
        self.assertEqual(self.state()["status"], "COMPLETED")

    def test_concurrent_scheduled_and_trader_launches_only_one(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(guard.begin, DATE) for _ in range(2)]
            results = sorted(f.result() for f in futures)
        self.assertEqual(results, [0, 20])
        self.assertEqual(self.state()["attempts"], 1)
        self.assertEqual(self.state()["status"], "RUNNING")


class TraderScheduleTests(unittest.TestCase):
    def setUp(self):
        source = (ROOT/"momentum_trader_v1_10_runtime_audit.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "post_close_review_due_target")
        self.close = datetime(2026, 10, 16, 20, 0, tzinfo=timezone.utc)
        self.state = {}
        self.namespace = {
            "POST_CLOSE_REVIEW_ENABLED": True, "MARKET_TZ": timezone.utc,
            "POST_CLOSE_REVIEW_DELAY_MINUTES": 5, "timedelta": timedelta,
            "timezone": timezone, "load_post_close_review_state": lambda: self.state,
            "market_session_close_utc": lambda _: self.close,
            "review_retry_decision": review_retry_decision,
        }
        exec(compile(ast.Module(body=[node], type_ignores=[]), "<trader pure test>", "exec"), self.namespace)
        self.fn = self.namespace["post_close_review_due_target"]

    def test_failed_review_defers_to_cooldown(self):
        now = self.close+timedelta(minutes=15)
        self.state = {"review_date":DATE, "status":"FAILED", "attempts":1,
                      "finished_at":now.isoformat()}
        self.assertEqual(self.fn(now), now+timedelta(minutes=FAILED_RETRY_COOLDOWN_MINUTES))

    def test_exhausted_review_is_not_rescheduled(self):
        now = self.close+timedelta(minutes=45)
        self.state = {"review_date":DATE, "status":"FAILED", "attempts":93,
                      "finished_at":now.isoformat()}
        self.assertIsNone(self.fn(now))

    def test_new_session_runs_close_plus_delay(self):
        now = self.close+timedelta(minutes=7)
        self.state = {"review_date":"2026-10-15", "status":"FAILED","attempts":93}
        self.assertEqual(self.fn(now), self.close+timedelta(minutes=5))


class BatchRunnerContractTests(unittest.TestCase):
    def test_exit_codes_and_stage_evidence_are_distinct(self):
        batch=(ROOT/"run_daily_model_review.bat").read_text(encoding="utf-8")
        self.assertIn("if errorlevel 22 goto :retry_cooldown", batch)
        self.assertIn("if errorlevel 21 goto :retry_exhausted", batch)
        self.assertIn("if errorlevel 20 goto :already_done", batch)
        self.assertIn("--stage %FAILSTAGE%", batch)
        self.assertIn("exit /b 21", batch)
        self.assertIn("exit /b 22", batch)
        for name in ("bundle", "evidence", "model_review", "proposal_publish", "github_sync"):
            self.assertIn("set FAILSTAGE="+name, batch)


if __name__ == "__main__":
    unittest.main()
