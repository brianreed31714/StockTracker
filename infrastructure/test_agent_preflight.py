"""Prove the deployed agent invokes the contract before stopping any process."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from infrastructure.registry_contract import RegistryError

ROOT = Path(__file__).resolve().parents[1]
if (ROOT / "stocktracker_deployment_agent.py").exists():
    import stocktracker_deployment_agent as agent
    FILE = "momentum_dashboard_v1_3_agentic.py"
    PROPOSAL = "P-STOCK-20261018-CONTRACT-TEST"
else:
    import deployment_agent as agent
    FILE = "cryptotracker_dashboard_v11_8_2.py"
    PROPOSAL = "P-20261018-CONTRACT-TEST"


class AgentRegistryHookTests(unittest.TestCase):
    def request(self):
        return {"status": "READY_TO_DEPLOY", "proposal_id": PROPOSAL,
                "commit": "a" * 40, "components": ["dashboard"],
                "files": {"dashboard": FILE}}

    def test_agent_invokes_contract_for_approved_request(self):
        with patch.object(agent, "run", return_value=SimpleNamespace(returncode=0, stdout="same-blob\n")), \
             patch.object(agent, "release_preflight", return_value={}) as preflight, \
             patch.object(agent, "enforce_commit_release_scope", return_value={}) as commit_scope:
            proposal_id, commit, targets = agent.validate_request(self.request())
        preflight.assert_called_once_with(agent.ROOT, ["dashboard"], {"dashboard": FILE})
        commit_scope.assert_called_once_with(agent.ROOT, "a" * 40, ["dashboard"])
        self.assertEqual(proposal_id, PROPOSAL)
        self.assertIn("dashboard", targets)

    def test_invalid_pending_request_is_quarantined_without_retries(self):
        with TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "P-STOCK-TEST-001.json").write_text(json.dumps(self.request()), encoding="utf-8")
            with patch.object(agent, "AUTO_DEPLOY", True), \
                 patch.object(agent, "REQUEST_DIR", folder), \
                 patch.object(agent, "pull_repo"), \
                 patch.object(agent, "processed_requests", return_value={}), \
                 patch.object(agent, "load_manifest", return_value={}), \
                 patch.object(agent, "deploy", side_effect=RegistryError("blocked")), \
                 patch.object(agent, "mark_processed") as processed, \
                 patch.object(agent, "push"), \
                 patch.object(agent, "log"):
                agent.scan_once()
            self.assertEqual(processed.call_args.args[:2], (PROPOSAL, "VALIDATION_FAILED"))

    def test_unchanged_failed_approval_is_skipped_but_new_commit_can_revalidate(self):
        with TemporaryDirectory() as temp:
            folder = Path(temp)
            path = folder / "P-STOCK-TEST-001.json"
            request = self.request()
            path.write_text(json.dumps(request), encoding="utf-8")
            done = {PROPOSAL: {"status": "VALIDATION_FAILED", "commit": request["commit"]}}
            with patch.object(agent, "AUTO_DEPLOY", True), \
                 patch.object(agent, "REQUEST_DIR", folder), \
                 patch.object(agent, "pull_repo"), \
                 patch.object(agent, "processed_requests", return_value=done), \
                 patch.object(agent, "deploy") as deploy:
                agent.scan_once()
                deploy.assert_not_called()
                request["commit"] = "b" * 40
                path.write_text(json.dumps(request), encoding="utf-8")
                agent.scan_once()
                deploy.assert_called_once()

    def test_disabled_deployment_preserves_read_only_host_observation(self):
        with patch.object(agent, "AUTO_DEPLOY", False), \
             patch.object(agent, "_observe_host_read_only") as observe, \
             patch.object(agent, "pull_repo") as pull, \
             patch.object(agent, "deploy") as deploy, \
             patch.object(agent, "mark_processed") as mark:
            agent.scan_once()
        observe.assert_called_once_with()
        pull.assert_not_called()
        deploy.assert_not_called()
        mark.assert_not_called()

    def test_host_observation_is_windows_only_and_uses_fresh_child(self):
        with patch.object(agent.os, "name", "posix"), \
             patch("infrastructure.fresh_attestation_runner.run_fresh_host_attestation") as child:
            agent._observe_host_read_only()
            child.assert_not_called()
        with patch.object(agent.os, "name", "nt"), \
             patch("infrastructure.fresh_attestation_runner.run_fresh_host_attestation",
                   return_value={"status": "HOST_CLAIM_ONLY"}) as child:
            agent._observe_host_read_only()
            child.assert_called_once_with(agent.ROOT)

    def test_invalid_release_does_not_stop_anything(self):
        with patch.object(agent, "stop_active") as stop, \
             patch.object(agent, "load_manifest", return_value={}):
            with self.assertRaises(ValueError):
                agent.deploy(ROOT / "nonexistent-request.json", {"status": "INVALID"})
            stop.assert_not_called()

    def test_supervisor_acknowledgement_is_not_declared_healthy(self):
        source = Path(agent.__file__).read_text(encoding="utf-8")
        self.assertIn('"verification_status": "UNVERIFIED"', source)
        self.assertIn("runtime health remains UNVERIFIED", source)
        self.assertNotIn('log(f"{pid}: deployment successful")', source)

    def test_registry_safety_failure_precedes_process_stop(self):
        with patch.object(agent, "run", return_value=SimpleNamespace(returncode=0, stdout="same-blob\n")), \
             patch.object(agent, "release_preflight", side_effect=RegistryError("safety gate")), \
             patch.object(agent, "stop_active") as stop, \
             patch.object(agent, "load_manifest", return_value={}):
            with self.assertRaisesRegex(RegistryError, "safety gate"):
                agent.deploy(ROOT / "nonexistent-request.json", self.request())
            stop.assert_not_called()


if __name__ == "__main__":
    unittest.main()
