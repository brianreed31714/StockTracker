"""Exact runtime version reconciliation; do not confuse script family with deployed version."""
from __future__ import annotations

import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

from infrastructure.runtime_inventory import compare_expected_script, associate_process


class ScriptVersionTests(unittest.TestCase):
    def test_local_active_manifest_overrides_old_stock_fallback(self):
        component = {
            "script_pattern": "momentum_trader_*.py",
            "entrypoint": "momentum_trader_v1_9_zpta_shadow.py",
            "manifest_key": "trader",
            "config_key": "STOCKTRACKER_ACTIVE_TRADER",
        }
        manifest = {"files": {"trader": "momentum_trader_v1_10_runtime_audit.py"}}
        tracked = {"STOCKTRACKER_ACTIVE_TRADER": "momentum_trader_v1_9_zpta_shadow.py"}
        observed = {"state": "OBSERVED", "script": "momentum_trader_v1_10_runtime_audit.py"}
        result = compare_expected_script(component, observed, manifest, tracked)
        self.assertEqual(result["state"], "MATCHED")
        self.assertEqual(result["expected_source"], "local_active_release_manifest")
        self.assertFalse(result["code_digest_verified"])

    def test_old_trader_is_detected_even_when_family_matches(self):
        component = {
            "script_pattern": "momentum_trader_*.py",
            "entrypoint": "momentum_trader_v1_9_zpta_shadow.py",
            "manifest_key": "trader",
            "config_key": "STOCKTRACKER_ACTIVE_TRADER",
        }
        manifest = {"files": {"trader": "momentum_trader_v1_10_runtime_audit.py"}}
        observed = {"state": "OBSERVED", "script": "momentum_trader_v1_9_zpta_shadow.py"}
        self.assertEqual(compare_expected_script(component, observed, manifest, {})["state"], "MISMATCH")

    def test_configured_smart_money_v23_is_expected_without_manifest_entry(self):
        component = {
            "script_pattern": "smart_money_monitor_*.py",
            "entrypoint": "SmartMoneyMonitor/smart_money_monitor_v2_3_feed_health_audit.py",
            "config_key": "SUPERVISOR_SMART_MONEY_SCRIPT",
        }
        tracked = {"SUPERVISOR_SMART_MONEY_SCRIPT": "SmartMoneyMonitor/smart_money_monitor_v2_3_feed_health_audit.py"}
        observed = {"state": "OBSERVED", "script": "smart_money_monitor_v2_3_feed_health_audit.py"}
        result = compare_expected_script(component, observed, {"files": {"trader": "auto_trader_with_alerts_v11_10_research_fairness.py"}}, tracked)
        self.assertEqual(result["state"], "MATCHED")
        self.assertEqual(result["expected_source"], "tracked_config_fallback")

    def test_unknown_process_identity_is_unverified_not_success(self):
        component = {"script_pattern": "momentum_dashboard_*.py", "entrypoint": "momentum_dashboard_v1_3_agentic.py"}
        self.assertEqual(compare_expected_script(component, {"state": "UNKNOWN"}, {}, {})["state"], "UNVERIFIED")

    def test_direct_process_match_exposes_specific_script_without_full_command(self):
        component = {"role": "service", "script_pattern": "momentum_trader_*.py"}
        process = {"pid": 34140, "command": f'python.exe "{ROOT / "momentum_trader_v1_10_runtime_audit.py"}" --token=secret' , "started_utc": ""}
        result = associate_process(component, [process], {})
        self.assertEqual(result["state"], "OBSERVED")
        self.assertEqual(result["script"], "momentum_trader_v1_10_runtime_audit.py")
        self.assertNotIn("secret", str(result))

    def test_script_argument_is_not_another_launched_script(self):
        component = {"role": "service", "script_pattern": "momentum_trader_*.py"}
        process = {"pid": 75, "command": f'python "{ROOT / "momentum_trader_v1_9_zpta_shadow.py"}" "{ROOT / "momentum_trader_v1_10_runtime_audit.py"}"' }
        self.assertEqual(associate_process(component, [process], {})["state"], "OBSERVED")


if __name__ == "__main__":
    unittest.main()
