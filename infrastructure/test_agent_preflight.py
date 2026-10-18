"""Prove the deployed agent invokes the contract before stopping any process."""
from __future__ import annotations

from pathlib import Path
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

    def test_invalid_release_does_not_stop_anything(self):
        with patch.object(agent, "stop_active") as stop, \
             patch.object(agent, "load_manifest", return_value={}):
            with self.assertRaises(ValueError):
                agent.deploy(ROOT / "nonexistent-request.json", {"status": "INVALID"})
            stop.assert_not_called()

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
