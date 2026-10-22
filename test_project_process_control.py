"""Non-destructive tests for project-scoped process selection."""
import unittest
from unittest.mock import patch
import project_process_control as ctl

class ProcessControlTests(unittest.TestCase):
    def test_only_project_service_names_selected(self):
        processes = [
            {"ProcessId": 10, "CommandLine": "python momentum_trader_v1_10_runtime_audit.py"},
            {"ProcessId": 11, "CommandLine": "python auto_trader_with_alerts_v11_10_research_fairness.py"},
            {"ProcessId": 12, "CommandLine": "python stocktracker_deployment_agent.py"},
            {"ProcessId": 13, "CommandLine": "python stocktracker_supervisor.py"},
            {"ProcessId": 14, "CommandLine": "python -m streamlit run momentum_dashboard_v1_3_agentic.py"},
            {"ProcessId": 15, "CommandLine": "python -m streamlit run cryptotracker_dashboard_v11_8_2.py"},
            {"ProcessId": 16, "CommandLine": "python xom_geo_feed_v1_1_agentic.py"},
            {"ProcessId": 17, "CommandLine": "python SmartMoneyMonitor/smart_money_monitor_v2_2_1_campaign_strength.py"},
        ]
        with patch.object(ctl, "_processes",return_value=processes):
            self.assertEqual({p for p,_ in ctl.project_services("stock")},{10,14,16})
            self.assertEqual({p for p,_ in ctl.project_services("crypto")},{11,15,17})

    def test_supervisor_does_not_confuse_similarly_named_scripts(self):
        other = [
            "python deployment_agent.py",
            "python my_stocktracker_deployment_agent.py",
            "python stocktracker_deployment_agent.py.backup",
        ]
        self.assertFalse(ctl.exact_script_running(other, "stocktracker_deployment_agent.py"))
        other.append("python C:\\StockTracker\\stocktracker_deployment_agent.py")
        self.assertTrue(ctl.exact_script_running(other, "stocktracker_deployment_agent.py"))

    def test_exact_identity_of_trader_geo_and_dashboard(self):
        lines = [
            "python C:\\StockTracker\\momentum_trader_v1_10_runtime_audit.py",
            "python xom_geo_feed_v1_1_agentic.py",
            "python -m streamlit run C:\\StockTracker\\momentum_dashboard_v1_3_agentic.py",
        ]
        for name in ("momentum_trader_v1_10_runtime_audit.py",
                     "xom_geo_feed_v1_1_agentic.py",
                     "momentum_dashboard_v1_3_agentic.py"):
            self.assertTrue(ctl.exact_script_running(lines, name))
        self.assertFalse(ctl.exact_script_running(lines, "momentum_trader_v1_9_zpta_shadow.py"))
        self.assertFalse(ctl.exact_script_running(lines, "cryptotracker_dashboard_v11_8_2.py"))

    def test_reject_broad_script_marker(self):
        with self.assertRaises(ValueError):
            ctl.exact_script_running([], "momentum_trader")

    def test_false_substring_not_matched(self):
        with patch.object(ctl,"_processes",return_value=[
            {"ProcessId":100,"CommandLine":"python my_momentum_trader_v1_10_runtime_audit.py.backup"},
        ]):
            self.assertEqual(ctl.project_services("stock"),[])

if __name__ == "__main__":
    unittest.main()
