"""Sanitized identity diagnostic tests; no real process inspection or termination."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from infrastructure.activate_review_repair import TRADER_NAME
from infrastructure.diagnose_trader_activation import diagnostic_report


def sample_snapshot(pid=34140):
    return {
        "components": {
            "trader": {
                "process": {
                    "state": "OBSERVED",
                    "pids": [pid],
                    "identification": "command_line",
                },
                "script_version": {"state": "MATCHED"},
            }
        },
        "active_manifest_files": {"trader": TRADER_NAME},
    }


def proc(pid, cmd, start="2026-10-17T03:47:45+00:00"):
    return {"pid": pid, "command": cmd, "started_utc": start}


class ReadOnlyDiagnosisTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.absolute = str(self.root / TRADER_NAME)

    def test_correct_absolute_script_matches_inventory(self):
        p = proc(34140, f'python.exe "{self.absolute}"')
        result = diagnostic_report(self.root, sample_snapshot(), [p], {})
        self.assertEqual(result["decision"], "IDENTITIES_AGREE")
        self.assertEqual(result["strict_identity_pids"], [34140])
        self.assertEqual(result["candidate_processes"][0]["executed_script_category"],
                         "EXACT_TRADER_SCRIPT_PATH")

    def test_inventory_observed_but_relative_command_unattested(self):
        p = proc(34140, f'python.exe {TRADER_NAME}')
        result = diagnostic_report(self.root, sample_snapshot(), [p], {})
        self.assertEqual(result["decision"], "INVENTORY_PID_LACKS_STRICT_PROVENANCE")
        self.assertEqual(result["strict_identity_pids"], [])
        self.assertEqual(result["candidate_processes"][0]["executed_script_category"],
                         "RELATIVE_TRADER_SCRIPT_NO_PATH_AUTHORITY")

    def test_inventory_observed_but_hidden_commandline_unattested(self):
        result = diagnostic_report(self.root, sample_snapshot(),
                                   [proc(34140, "")], {})
        self.assertEqual(result["decision"], "INVENTORY_PID_LACKS_STRICT_PROVENANCE")
        self.assertEqual(result["candidate_processes"][0]["executed_script_category"],
                         "COMMAND_LINE_HIDDEN")

    def test_running_parent_python_mentions_trader_as_argument_not_a_candidate(self):
        fake = proc(32760, f'python.exe -m other_app --source "{self.absolute}"')
        real = proc(34140, f'python.exe "{self.absolute}"')
        result = diagnostic_report(self.root, sample_snapshot(), [fake, real], {})
        self.assertEqual(result["decision"], "IDENTITIES_AGREE")
        categories = {p["pid"]: p["executed_script_category"]
                      for p in result["candidate_processes"]}
        self.assertEqual(categories[32760],
                         "TRADER_NAME_IN_ARGUMENTS_NOT_EXECUTED_SCRIPT")

    def test_foreign_script_is_not_accepted_or_exposed(self):
        foreign = str(self.root.parent / "Different" / TRADER_NAME)
        result = diagnostic_report(self.root, sample_snapshot(),
                                   [proc(34140, f'python.exe "{foreign}"')], {})
        self.assertEqual(result["strict_identity_error"], "FOREIGN_TRADER_PATH_DETECTED")
        text = json.dumps(result)
        self.assertNotIn(foreign, text)
        self.assertNotIn(str(self.root), text)

    def test_supervisor_attestation_for_relative_script(self):
        entry = {"time": "2026-10-17T03:47:45",
                 "script": TRADER_NAME, "label": "Trader"}
        started = datetime.fromisoformat(entry["time"]).astimezone(timezone.utc).isoformat()
        result = diagnostic_report(
            self.root, sample_snapshot(),
            [proc(34140, f'python.exe {TRADER_NAME}', start=started)],
            {34140: entry},
        )
        self.assertEqual(result["decision"], "IDENTITIES_AGREE")
        self.assertTrue(result["candidate_processes"][0]["supervisor_start_provenance_matched"])

    def test_diagnosis_never_echoes_trading_secrets_or_raw_commandline(self):
        command = f'python.exe "{self.absolute}" --alpaca-secret-key=NEVER_ECHO'
        result = diagnostic_report(self.root, sample_snapshot(),
                                   [proc(34140, command)], {})
        text = json.dumps(result)
        self.assertNotIn("NEVER_ECHO", text)
        self.assertNotIn("--alpaca", text)
        self.assertNotIn(command, text)
        self.assertEqual(result["mode"], "READ_ONLY_NO_PROCESS_CHANGES")

    def test_pid_disagreement_is_distinguished_from_missing_provenance(self):
        result = diagnostic_report(
            self.root, sample_snapshot(pid=34140),
            [proc(10001, f'python.exe "{self.absolute}"'),
             proc(34140, "python.exe another_script.py")], {},
        )
        self.assertEqual(result["decision"], "INVENTORY_AND_STRICT_PID_DISAGREE")
        self.assertEqual(result["strict_identity_pids"], [10001])

    def test_two_matching_processes_are_not_declared_safe(self):
        result = diagnostic_report(
            self.root, sample_snapshot(),
            [proc(34140, f'python.exe "{self.absolute}"'),
             proc(34141, f'python.exe "{self.absolute}"')], {},
        )
        self.assertEqual(result["decision"], "MULTIPLE_STRICT_TRADERS")

if __name__ == "__main__":
    unittest.main()
