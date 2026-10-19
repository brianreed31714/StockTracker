"""Process provenance regression tests, without stopping a real Windows PID."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from infrastructure.activate_review_repair import (
    ActivationBlocked, TRADER_NAME, matching_traders, _trader_script_argument,
)


def p(root: Path, pid: int, script: str, *, started: str = "2026-10-17T03:47:46+00:00") -> dict:
    return {"pid": pid, "command": script, "started_utc": started}


class ProcessCommandProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.full = str(self.root / TRADER_NAME)

    def test_absolute_command_targets_only_real_python_script_argument(self):
        proc = p(self.root, 34140, f'python.exe "{self.full}"')
        rows = matching_traders([proc], self.root, launches={})
        self.assertEqual([r["pid"] for r in rows], [34140])
        self.assertEqual(rows[0]["provenance"], "exact_executable_script_path")

    def test_ignore_unrelated_python_module_that_mentions_script(self):
        arg = f'python.exe -m other_test_runner --note "{self.full}"'
        self.assertEqual(matching_traders([p(self.root, 9876, arg)], self.root, launches={}), [])

    def test_ignore_python_inline_command_that_mentions_script(self):
        arg = 'python.exe -c "print(1)" ' + TRADER_NAME
        self.assertEqual(matching_traders([p(self.root, 9876, arg)], self.root, launches={}), [])

    def test_ignore_other_python_script_with_trader_as_extra_argument(self):
        arg = f'python.exe dashboard.py "{self.full}"'
        self.assertEqual(matching_traders([p(self.root, 32760, arg)], self.root, launches={}), [])

    def test_reject_foreign_absolute_script_and_do_not_pick_its_pid(self):
        arg = f'python.exe "{self.root.parent / "OtherRepo" / TRADER_NAME}"'
        with self.assertRaises(ActivationBlocked):
            matching_traders([p(self.root, 9932, arg)], self.root, launches={})

    def test_relative_name_without_independent_log_is_not_trusted(self):
        arg = f"python.exe {TRADER_NAME}"
        self.assertEqual(matching_traders([p(self.root, 34140, arg)], self.root, launches={}), [])

    def test_relative_name_with_matching_supervisor_log_is_accepted(self):
        entry = {"time": "2026-10-17T03:47:45", "script": TRADER_NAME, "label": "Trader"}
        # Naive supervisor log timestamps use the current host timezone.
        stamp = datetime.fromisoformat(entry["time"]).astimezone(timezone.utc).isoformat()
        proc = p(self.root, 34140, f"python.exe {TRADER_NAME}", started=stamp)
        found = matching_traders([proc], self.root, launches={34140: entry})
        self.assertEqual([r["pid"] for r in found], [34140])
        self.assertEqual(found[0]["provenance"], "supervisor_pid_start_time")

    def test_hidden_command_with_matching_supervisor_evidence(self):
        entry = {"time": "2026-10-17T03:47:45", "script": TRADER_NAME, "label": "Trader"}
        stamp = datetime.fromisoformat(entry["time"]).astimezone(timezone.utc).isoformat()
        proc = p(self.root, 34140, "", started=stamp)
        self.assertEqual([r["pid"] for r in matching_traders([proc], self.root, launches={34140: entry})], [34140])

    def test_pid_reuse_does_not_allow_arbitrary_python_termination(self):
        entry = {"time": "2026-10-17T03:47:45", "script": TRADER_NAME, "label": "Trader"}
        stamp = (datetime.fromisoformat(entry["time"]).astimezone(timezone.utc)
                 + timedelta(minutes=10)).isoformat()
        proc = p(self.root, 34140, f"python.exe {TRADER_NAME}", started=stamp)
        self.assertEqual(matching_traders([proc], self.root, launches={34140: entry}), [])

    def test_wrong_supervisor_label_is_not_enough(self):
        entry = {"time": "2026-10-17T03:47:45", "script": TRADER_NAME, "label": "Geo Feed"}
        stamp = datetime.fromisoformat(entry["time"]).astimezone(timezone.utc).isoformat()
        proc = p(self.root, 34140, f"python.exe {TRADER_NAME}", started=stamp)
        self.assertEqual(matching_traders([proc], self.root, launches={34140: entry}), [])

    def test_wrong_log_script_not_enough(self):
        entry = {"time": "2026-10-17T03:47:45", "script": "momentum_trader_v1_9_zpta_shadow.py", "label": "Trader"}
        stamp = datetime.fromisoformat(entry["time"]).astimezone(timezone.utc).isoformat()
        proc = p(self.root, 34140, f"python.exe {TRADER_NAME}", started=stamp)
        self.assertEqual(matching_traders([proc], self.root, launches={34140: entry}), [])

    def test_relative_path_other_script_is_not_trader(self):
        entry = {"time": "2026-10-17T03:47:45", "script": TRADER_NAME, "label": "Trader"}
        stamp = datetime.fromisoformat(entry["time"]).astimezone(timezone.utc).isoformat()
        proc = p(self.root, 34140, "python.exe stocktracker_supervisor.py", started=stamp)
        self.assertEqual(matching_traders([proc], self.root, launches={34140: entry}), [])

    def test_argument_parser_skips_flag_not_exec_file(self):
        self.assertEqual(_trader_script_argument(f'python.exe -u "{self.full}"'), self.full)
        self.assertIsNone(_trader_script_argument(f'python.exe -m module "{self.full}"'))
        self.assertIsNone(_trader_script_argument('powershell.exe python.exe some.py'))

    def test_no_raw_argv_output_leaks_secrets(self):
        arg = f'python.exe "{self.full}" --api-key=do-not-print'
        row = matching_traders([p(self.root, 34140, arg)], self.root, launches={})[0]
        self.assertEqual(row["pid"], 34140)
        # Process details are local/ephemeral and are not printed as telemetry.
        self.assertNotIn("do-not-print", row["provenance"])


if __name__ == "__main__":
    unittest.main()
