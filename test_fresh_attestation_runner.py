"""Regression tests for fresh-process host attestation invocation."""
import json
from pathlib import Path
from types import SimpleNamespace
import subprocess
import unittest
from unittest.mock import patch

from infrastructure.fresh_attestation_runner import run_fresh_host_attestation


class FreshAttestationRunnerTests(unittest.TestCase):
    def test_launches_fresh_fixed_module_without_shell_or_restart(self):
        receipt = {"state": "HOST_PROCESSES_STABLE_SOURCE_ONLY",
                   "remote_publish": "PUBLISHED"}
        with patch("infrastructure.fresh_attestation_runner.subprocess.run",
                   return_value=SimpleNamespace(returncode=0, stdout=json.dumps(receipt))) as run:
            result = run_fresh_host_attestation(Path("."))
        cmd = run.call_args.args[0]
        self.assertEqual(cmd[1:3], ["-m", "infrastructure.windows_activation_attestation"])
        self.assertIn("--notify", cmd)
        self.assertEqual(cmd[3], "--root")
        self.assertEqual(run.call_args.kwargs["cwd"], Path(".").resolve())
        self.assertNotIn("shell", run.call_args.kwargs)
        self.assertTrue(run.call_args.kwargs["capture_output"])
        self.assertEqual(result["status"], "HOST_CLAIM_ONLY")
        self.assertFalse(result["loaded_runtime_verified"])

    def test_bad_json_fails_closed(self):
        with patch("infrastructure.fresh_attestation_runner.subprocess.run",
                   return_value=SimpleNamespace(returncode=0, stdout="not json")):
            result = run_fresh_host_attestation(Path("."))
        self.assertEqual(result["status"], "UNVERIFIED")

    def test_nonzero_exit_fails_closed(self):
        with patch("infrastructure.fresh_attestation_runner.subprocess.run",
                   return_value=SimpleNamespace(returncode=2, stdout='{"state":"UNVERIFIED"}')):
            result = run_fresh_host_attestation(Path("."))
        self.assertEqual(result["status"], "UNVERIFIED")

    def test_timeout_fails_closed(self):
        with patch("infrastructure.fresh_attestation_runner.subprocess.run",
                   side_effect=subprocess.TimeoutExpired("python", 150)):
            result = run_fresh_host_attestation(Path("."))
        self.assertEqual(result["status"], "UNVERIFIED")

    def test_invalid_timeout_rejected(self):
        with self.assertRaises(ValueError):
            run_fresh_host_attestation(Path("."), timeout_seconds=0)


if __name__ == "__main__":
    unittest.main()
