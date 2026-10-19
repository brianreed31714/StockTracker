"""Windows-safe independent cwd+creation-time verification for relative trader.

Injected process data only; these tests never stop, restart, or communicate
with a real trading process. psutil is a read-only dependency.
"""
from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
import unittest

from infrastructure.activate_review_repair import (
    TRADER_NAME, relative_process_cwd_evidence, matching_traders,
)
from infrastructure.diagnose_trader_activation import diagnostic_report


class CwdIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.started = datetime(2026, 10, 17, 3, 47, 45, tzinfo=timezone.utc)
        self.process = {
            "pid": 34140,
            "command": f"python.exe {TRADER_NAME}",
            "started_utc": self.started.isoformat(),
        }

    def mocked(self, cwd=None, created=None):
        obj = Mock()
        obj.oneshot.return_value = nullcontext()
        obj.cwd.return_value = str(cwd or self.root)
        obj.create_time.return_value = (
            created if created is not None else self.started.timestamp()
        )
        return obj

    def test_relative_trader_cwd_and_pid_time_verified(self):
        with patch("psutil.Process", return_value=self.mocked()) as read:
            outcome = relative_process_cwd_evidence(self.process, self.root)
            matched = matching_traders([self.process], self.root, launches={})
        self.assertEqual(outcome, "MATCHED")
        self.assertEqual([x["pid"] for x in matched], [34140])
        self.assertEqual(matched[0]["provenance"], "process_cwd_and_start_time")
        self.assertEqual(read.call_args.args, (34140,))

    def test_relative_trader_from_other_working_directory_never_accepted(self):
        other = self.root.parent / "OtherRepo"
        with patch("psutil.Process", return_value=self.mocked(cwd=other)):
            self.assertEqual(relative_process_cwd_evidence(self.process, self.root),
                             "FOREIGN_WORKING_DIRECTORY")
            self.assertEqual(matching_traders([self.process], self.root, launches={}), [])

    def test_pid_reuse_blocks_relative_trader(self):
        created = (self.started + timedelta(minutes=20)).timestamp()
        with patch("psutil.Process", return_value=self.mocked(created=created)):
            self.assertEqual(relative_process_cwd_evidence(self.process, self.root),
                             "PID_CREATION_TIME_MISMATCH")
            self.assertEqual(matching_traders([self.process], self.root, launches={}), [])

    def test_psutil_access_denied_fails_closed(self):
        import psutil
        with patch("psutil.Process", side_effect=psutil.AccessDenied(pid=34140)):
            self.assertEqual(relative_process_cwd_evidence(self.process, self.root),
                             "CWD_ACCESS_UNAVAILABLE")
            self.assertEqual(matching_traders([self.process], self.root, launches={}), [])

    def test_no_process_start_timestamp_fails_closed(self):
        proc = {**self.process, "started_utc": ""}
        with patch("psutil.Process") as constructor:
            self.assertEqual(relative_process_cwd_evidence(proc, self.root),
                             "UNVERIFIED_START_TIME")
            constructor.assert_not_called()

    def test_readonly_diagnostic_does_not_output_directory_or_argv(self):
        state = {
            "components": {
                "trader": {
                    "process": {"state": "OBSERVED", "pids": [34140],
                                "identification": "command_line"},
                    "script_version": {"state": "MATCHED"},
                }
            },
            "active_manifest_files": {"trader": TRADER_NAME},
        }
        proc = {**self.process, "command": f"python.exe {TRADER_NAME} --secret=NEVER_ECHO"}
        with patch("psutil.Process", return_value=self.mocked()):
            result = diagnostic_report(self.root, state, [proc], {})
        self.assertEqual(result["decision"], "IDENTITIES_AGREE")
        self.assertEqual(result["candidate_processes"][0]["process_cwd_evidence"], "MATCHED")
        text = str(result)
        self.assertNotIn("NEVER_ECHO", text)
        self.assertNotIn(str(self.root), text)

    def test_absolute_executed_other_project_rejected_even_with_matching_cwd(self):
        foreign = str(self.root.parent / "OtherProject" / TRADER_NAME)
        proc = {**self.process, "command": f'python.exe "{foreign}"'}
        with patch("psutil.Process") as process_constructor:
            from infrastructure.activate_review_repair import ActivationBlocked
            with self.assertRaises(ActivationBlocked):
                matching_traders([proc], self.root, launches={})
            process_constructor.assert_not_called()


if __name__ == "__main__":
    unittest.main()
