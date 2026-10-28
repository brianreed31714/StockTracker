"""No-network tests: GitHub status branch must never touch main or leak local data."""
from __future__ import annotations
import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

from infrastructure import host_status_publisher as publisher
from infrastructure import windows_activation_attestation as attest

HEAD = "f"*40
T0 = datetime(2026, 10, 19, 21, 0, tzinfo=timezone.utc)


def sample(state="CODE_SYNCED_PROCESS_OBSERVED"):
    return {
        "git_head": HEAD,
        "state": state,
        "code_synced": True,
        "processes_stable": False,
        "eod_execution_verified": False,
        "observed_at_utc": T0.isoformat(),
        "fingerprint": {"trader": [1234, "C:\\PRIVATE\\Trader", "my_trader.py"]},
        "error": "SECRET_OPENAI_KEY",
        "positions": [{"symbol": "NVDA", "qty": 10000}],
        "account_id": "SENSITIVE_ACCOUNT",
    }


class HostSignalTests(unittest.TestCase):
    def test_strict_status_payload_contains_no_local_details(self):
        data = sample()
        clean = json.dumps(publisher.sanitized(data))
        for secret in ("C:\\PRIVATE", "1234", "NVDA", "SENSITIVE_ACCOUNT", "SECRET_OPENAI_KEY", "my_trader.py"):
            self.assertNotIn(secret, clean)
        self.assertIn("source_code_synced", clean)
        self.assertIn("broker_trade_health_verified", clean)
        self.assertNotIn("fingerprint", clean)

    def test_reject_unknown_status_sha_date_or_timezone(self):
        for key, val in [
            ("state", "POSITION_OPEN_SECRET"), ("git_head", "f" * 8),
            ("observed_at_utc", "2026-10-19T19:00:00"),
        ]:
            data = sample()
            data[key] = val
            with self.assertRaises(ValueError):
                publisher.sanitized(data)
        data = sample("EOD_EXECUTION_VERIFIED")
        data.update({"eod_execution_verified": True, "verified_review_date": "../../invalid"})
        with self.assertRaises(ValueError):
            publisher.sanitized(data)

    def test_task_success_is_not_eod_or_broker_proof(self):
        data = sample()
        data["daily_review_task_observation"] = {
            "status": "TASK_NAME_OBSERVED", "scheduler_state": "Ready",
            "last_run_utc": "2026-10-19T20:00:00+00:00",
            "last_task_result": 0, "eod_delivery_verified": True,
            "local_path": r"C:\\SECRET\\review.bat",
        }
        published = publisher.sanitized(data)
        self.assertEqual(published["daily_review_task_status"], "TASK_NAME_OBSERVED")
        self.assertEqual(published["daily_review_last_task_result"], 0)
        self.assertFalse(published["post_sync_eod_verified"])
        self.assertFalse(published["broker_trade_health_verified"])
        self.assertNotIn("SECRET", json.dumps(published))

    def test_task_invalid_provenance_fails_closed(self):
        for observation in (
            {"status": "TASK_NAME_OBSERVED", "scheduler_state": "Ready",
             "last_run_utc": "2026-10-20T20:00:00+00:00", "last_task_result": 0},
            {"status": "TASK_NAME_OBSERVED", "scheduler_state": "Ready",
             "last_run_utc": None, "last_task_result": True},
            {"status": "TASK_NAME_OBSERVED", "scheduler_state": "FAKE_SUCCESS",
             "last_run_utc": None, "last_task_result": 0},
        ):
            data = sample()
            data["daily_review_task_observation"] = observation
            published = publisher.sanitized(data)
            self.assertEqual(published["daily_review_task_status"], "UNVERIFIED")
            self.assertNotIn("daily_review_last_task_result", published)

    def test_new_branch_uses_git_plumbing_never_checkout_or_main_push(self):
        with tempfile.TemporaryDirectory() as temp:
            called = []
            def fake_git(root, args, data=None):
                called.append((args, data))
                if args[:2] == ["branch", "--show-current"]:
                    return "main"
                if args and args[0] == "ls-remote":
                    return ""
                if args and args[0] == "hash-object":
                    return "a" * 40
                if args and args[0] == "mktree":
                    return "b" * 40
                if "commit-tree" in args:
                    return "c" * 40
                if args and args[0] == "push":
                    return ""
                raise AssertionError(f"Unexpected Git operation: {args}")
            with patch.object(publisher, "_git", side_effect=fake_git):
                commit = publisher.publish(Path(temp), sample())
            self.assertEqual(commit, "c"*40)
            cmds = [args for args, _ in called]
            self.assertTrue(any(a[0] == "push" and a[-1].endswith(":refs/heads/stocktracker-host-status")
                                for a in cmds))
            self.assertFalse(any(a[0] in {"pull","reset","checkout","merge","add","commit","rebase"}
                                 for a in cmds))
            blob_data = next(data for args, data in called if args[0] == "hash-object")
            self.assertNotIn("SENSITIVE_ACCOUNT", blob_data)

    def test_existing_remote_must_be_single_file_and_non_fast_forward_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            calls = []
            def bad_git(root, args, data=None):
                calls.append(args[0])
                if args[0] == "branch":
                    return "main"
                if args[0] == "ls-remote":
                    return "a"*40 + "\trefs/heads/stocktracker-host-status"
                if args[0] == "fetch":
                    return ""
                if args[0] == "rev-parse":
                    return "a"*40
                if args[0] == "ls-tree":
                    return "extra-secret-file.txt\nstatus.json"
                raise AssertionError("Must fail before creating objects")
            with patch.object(publisher, "_git", side_effect=bad_git):
                with self.assertRaises(RuntimeError):
                    publisher.publish(Path(temp), sample())
            self.assertNotIn("push", calls)
            self.assertNotIn("hash-object", calls)

    def test_git_plumbing_stdin_is_raw_bytes_not_windows_crlf(self):
        result = subprocess.CompletedProcess(
            args=["git"], returncode=0, stdout=b"abc123\n", stderr=b"")
        entry = "100644 blob " + "a" * 40 + "\tstatus.json\n"
        with patch.object(publisher.subprocess, "run", return_value=result) as run:
            self.assertEqual(publisher._git(Path("test"), ["mktree"], data=entry),
                             "abc123")
        kwargs = run.call_args.kwargs
        self.assertEqual(kwargs["input"], entry.encode("utf-8"))
        self.assertNotIn("text", kwargs)
        self.assertTrue(kwargs["input"].endswith(b"status.json\n"))
        self.assertFalse(kwargs["input"].endswith(b"\r\n"))

    def test_exact_legacy_single_file_tree_migrates_by_fast_forward(self):
        with tempfile.TemporaryDirectory() as temp:
            calls = []
            def fake_git(root, args, data=None):
                calls.append((args, data))
                if args[:2] == ["branch", "--show-current"]:
                    return "main"
                if args[0] == "ls-remote":
                    return "a"*40 + "\trefs/heads/stocktracker-host-status"
                if args[0] == "fetch":
                    return ""
                if args[0] == "rev-parse":
                    return "a"*40
                if args[0] == "ls-tree":
                    self.assertIn("-z", args)
                    return "status.json\r\x00"
                if args[0] == "hash-object":
                    return "b"*40
                if args[0] == "mktree":
                    return "c"*40
                if "commit-tree" in args:
                    return "d"*40
                if args[0] == "push":
                    return ""
                raise AssertionError(f"Unexpected Git operation: {args}")
            with patch.object(publisher, "_git", side_effect=fake_git):
                self.assertEqual(publisher.publish(Path(temp), sample()), "d"*40)
            commit_args = next(args for args, _ in calls if "commit-tree" in args)
            self.assertIn("a"*40, commit_args)
            tree_data = next(data for args, data in calls if args[0] == "mktree")
            self.assertEqual(tree_data, "100644 blob " + "b"*40 + "\tstatus.json\n")
            self.assertTrue(any(args[0] == "push" for args, _ in calls))

    def test_invalid_legacy_tree_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as temp:
            calls = []
            def fake_git(root, args, data=None):
                calls.append(args[0])
                if args[0] == "branch":
                    return "main"
                if args[0] == "ls-remote":
                    return "a"*40 + "\trefs/heads/stocktracker-host-status"
                if args[0] == "fetch":
                    return ""
                if args[0] == "rev-parse":
                    return "a"*40
                if args[0] == "ls-tree":
                    return "status.json\r\x00other-file\x00"
                raise AssertionError(f"Unsafe Git operation: {args}")
            with patch.object(publisher, "_git", side_effect=fake_git):
                with self.assertRaises(RuntimeError):
                    publisher.publish(Path(temp), sample())
            self.assertNotIn("push", calls)
            self.assertNotIn("hash-object", calls)

    def test_sanitized_status_heartbeat_without_notification_spam(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            observations = {
                cid: {"process": {"state": "OBSERVED", "pids": [100+i],
                                  "started_utc": (T0-timedelta(minutes=15)).isoformat(),
                                  "script": cid+".py"},
                      "script_version": {"state": "MATCHED"}}
                for i, cid in enumerate(attest.REQUIRED_PROCESSES)
            }
            pushed = []
            notices = []
            def publish(_root, report):
                pushed.append(report["observed_at_utc"])
                return "c" * 40
            def notify(*args):
                notices.append(args)
                return True
            with patch.object(attest, "git_head", return_value=HEAD), \
                 patch.object(attest, "_head", return_value=HEAD), \
                 patch.object(attest, "_code_clean", return_value=True):
                for minutes in (0, 1, 2, 3, 362, 363):
                    receipt = attest.poll(
                        root, observation={"components": observations},
                        clock=T0+timedelta(minutes=minutes),
                        remote_publish=publish, notify=notify)
            # State changes at 2m, and a new sanitized heartbeat at 362m.
            self.assertEqual(len(pushed), 3)
            self.assertEqual(len(notices), 1)
            self.assertEqual(receipt["remote_publish"], "PUBLISHED")
            self.assertEqual(receipt["remote_published_at_utc"],
                             (T0+timedelta(minutes=362)).isoformat())

    def test_status_published_once_per_transition_without_any_real_network(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            observations = {
                cid: {"process": {"state": "OBSERVED", "pids": [100+i],
                                  "started_utc": (T0-timedelta(minutes=15)).isoformat(),
                                  "script": cid+".py"},
                      "script_version": {"state": "MATCHED"}}
                for i, cid in enumerate(attest.REQUIRED_PROCESSES)
            }
            calls = []
            def record(root, receipt):
                calls.append(receipt["state"])
                return "a"*40
            with patch.object(attest, "git_head", return_value=HEAD), \
                 patch.object(attest, "_head", return_value=HEAD), \
                 patch.object(attest, "_code_clean", return_value=True):
                for minutes in (0, 1, 2, 3):
                    receipt = attest.poll(
                        root, observation={"components": observations},
                        clock=T0+timedelta(minutes=minutes), remote_publish=record)
            self.assertEqual(calls, ["CODE_SYNCED_PROCESS_OBSERVED",
                                     "HOST_PROCESSES_STABLE_SOURCE_ONLY"])
            self.assertEqual(receipt["remote_publish"], "PUBLISHED")
            self.assertEqual(receipt["remote_key"].split(":")[0], HEAD)


if __name__ == "__main__":
    unittest.main()
