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

    def test_false_substring_not_matched(self):
        with patch.object(ctl,"_processes",return_value=[
            {"ProcessId":100,"CommandLine":"python my_momentum_trader_v1_10_runtime_audit.py.backup"},
        ]):
            self.assertEqual(ctl.project_services("stock"),[])

if __name__ == "__main__":
    unittest.main()
