"""Fast, destructive-free negative tests for the infrastructure contract."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from infrastructure.registry_contract import (
    RegistryError, validate_registry, release_preflight, change_impact,
)


ROOT = Path(__file__).resolve().parents[1]


class RegistryContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        data = json.loads((ROOT / "infrastructure/registry.json").read_text(encoding="utf-8"))
        self.registry = data
        all_paths = {data["settings_file"]}
        for item in data["components"]:
            all_paths.update(item["source_files"])
        for task in data["scheduled_tasks"]:
            all_paths.update([task["installer"], task["script"]])
        for rel in all_paths:
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            if rel == ".env.config":
                actual = (ROOT / rel).read_text(encoding="utf-8")
                path.write_text(actual, encoding="utf-8")
            elif path.suffix == ".py":
                path.write_text("PAPER_ONLY = True\npaper=True\nLIVE_TRADING = False\n", encoding="utf-8")
            else:
                path.write_text("placeholder\n", encoding="utf-8")
        self.save_registry()

    def save_registry(self):
        path = self.root / "infrastructure" / "registry.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.registry, indent=2), encoding="utf-8")

    def test_registry_valid_and_paper_only(self):
        result = validate_registry(self.root, check_local_safety=True)
        self.assertEqual(result["mode"], "PAPER_ONLY")

    def test_missing_source_rejected(self):
        target = self.root / self.registry["components"][0]["source_files"][0]
        target.unlink()
        with self.assertRaisesRegex(RegistryError, "missing"):
            validate_registry(self.root)

    def test_cross_project_task_rejected(self):
        self.registry["scheduled_tasks"][0]["name"] = "AnotherProject Supervisor"
        self.save_registry()
        with self.assertRaises(RegistryError):
            validate_registry(self.root)

    def test_dependency_cycle_rejected(self):
        components = {c["id"]: c for c in self.registry["components"]}
        components["supervisor"]["depends_on"] = ["trader"]
        components["trader"]["depends_on"].append("supervisor")
        self.save_registry()
        with self.assertRaisesRegex(RegistryError, "cycle"):
            validate_registry(self.root)

    def test_unsafe_path_rejected(self):
        self.registry["components"][0]["source_files"][0] = "../secrets.txt"
        self.save_registry()
        with self.assertRaises(RegistryError):
            validate_registry(self.root)

    def test_unknown_component_rejected_before_any_deployment(self):
        with self.assertRaises(RegistryError):
            release_preflight(self.root, ["unsafe_component"], {"unsafe_component": "unsafe.py"})

    def test_script_family_mismatch_rejected(self):
        with self.assertRaises(RegistryError):
            release_preflight(self.root, ["trader"], {"trader": "deployment_agent.py"})

    def test_paper_trader_release_with_matching_markers(self):
        component = next(c for c in self.registry["components"] if c["id"] == "trader")
        result = release_preflight(self.root, ["trader"], {"trader": component["entrypoint"]})
        self.assertEqual(result["project"], self.registry["project"])

    def test_paper_safety_marker_missing_rejected(self):
        component = next(c for c in self.registry["components"] if c["id"] == "trader")
        (self.root / component["entrypoint"]).write_text("print('not safe')\n", encoding="utf-8")
        with self.assertRaisesRegex(RegistryError, "paper-safety marker"):
            release_preflight(self.root, ["trader"], {"trader": component["entrypoint"]})

    def test_changed_shared_dependency_identifies_downstream_verification(self):
        if self.registry["project"] == "CryptoTracker":
            impact = change_impact(self.registry, ["SmartMoneyMonitor/solana_public_rpc_v23.py"])
            self.assertIn("smart_money", impact["verification_dependencies"])
            self.assertIn("dashboard", impact["verification_dependencies"])
        else:
            impact = change_impact(self.registry, ["xom_geo_feed_v1_1_agentic.py"])
            self.assertIn("geo_feed", impact["source_owners"])
            self.assertIn("trader", impact["verification_dependencies"])

    def test_unmapped_python_change_is_visible(self):
        impact = change_impact(self.registry, ["unexpected_new_engine.py"])
        self.assertEqual(impact["unmapped_python_files"], ["unexpected_new_engine.py"])

    def test_local_mode_override_blocks_release(self):
        if self.registry["project"] == "CryptoTracker":
            (self.root / ".env").write_text("LIVE_TRADING=true\n", encoding="utf-8")
            with self.assertRaisesRegex(RegistryError, "LIVE_TRADING"):
                validate_registry(self.root, check_local_safety=True)
        else:
            trader = next(c for c in self.registry["components"] if c["id"] == "trader")
            target = self.root / trader["entrypoint"]
            target.write_text("PAPER_ONLY = False\npaper=False\n", encoding="utf-8")
            with self.assertRaisesRegex(RegistryError, "paper-safety marker"):
                release_preflight(self.root, ["trader"], {"trader": trader["entrypoint"]})

    def test_protected_repo_config_change_rejected(self):
        if self.registry["project"] == "CryptoTracker":
            path = self.root / ".env.config"
            path.write_text(path.read_text().replace("LIVE_TRADING=false", "LIVE_TRADING=true"), encoding="utf-8")
            with self.assertRaisesRegex(RegistryError, "LIVE_TRADING"):
                validate_registry(self.root)


if __name__ == "__main__":
    unittest.main()
