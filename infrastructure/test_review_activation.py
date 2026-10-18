"""Non-destructive preflight and injected process tests for paper trader activation.

NO real Windows process is terminated. Verify that only one exact StockTrader
PID can be targeted; no Crypto, geo, dashboard, or supervisor restart commands.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import unittest

import infrastructure.activate_review_repair as activation


TRADER = activation.TRADER_NAME


def component(pid: int, script: str = TRADER) -> dict:
    return {
        "process": {"state": "OBSERVED", "pids": [pid]},
        "script_version": {
            "state": "MATCHED", "observed_script": script, "expected_script": script,
        },
    }


def snapshot(*, trader_pid: int = 34140) -> dict:
    return {
        "active_manifest_commit": "286dd941",
        "active_manifest_files": {"trader": TRADER},
        "components": {
            "supervisor": component(25084, "stocktracker_supervisor.py"),
            "deployment_agent": component(26720, "stocktracker_deployment_agent.py"),
            "geo_feed": component(43152, "xom_geo_feed_v1_1_agentic.py"),
            "trader": component(trader_pid),
            "dashboard": component(39440, "momentum_dashboard_v1_3_agentic.py"),
        },
        "tasks": [{"name": "StockTracker Daily Review", "state": "Ready"}],
    }


def process(root: Path, pid: int = 34140, script: str = TRADER) -> dict:
    return {
        "pid": pid,
        "command": f'python.exe "{root.resolve() / script}"',
        "started_utc": "2026-10-17T03:47:46+00:00",
    }


class ActivationPolicyTests(unittest.TestCase):
    def test_weekend_is_allowed(self):
        self.assertTrue(activation.outside_active_hours(datetime(2026,10,18,20,tzinfo=timezone.utc)))

    def test_market_day_is_blocked(self):
        self.assertFalse(activation.outside_active_hours(datetime(2026,10,19,17,tzinfo=timezone.utc)))

    def test_missing_component_fails_closed(self):
        s = snapshot()
        s["components"]["geo_feed"]["process"]["state"] = "UNKNOWN"
        with self.assertRaises(activation.ActivationBlocked):
            activation.require_observed_services(s, activation.REQUIRED_STOCK)

    def test_mismatched_script_fails_closed(self):
        s = snapshot()
        s["components"]["trader"]["script_version"]["state"] = "MISMATCH"
        with self.assertRaises(activation.ActivationBlocked):
            activation.require_observed_services(s, activation.REQUIRED_STOCK)

    def test_hidden_commandline_is_not_guessed(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            self.assertEqual(activation.matching_traders(
                [{"pid":34140, "command": "", "started_utc":"2026-10-17T00:00:00Z"}],
                root,
            ), [])

    def test_foreign_project_path_fails_closed(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            foreign = root.parent / "OtherProject" / TRADER
            with self.assertRaises(activation.ActivationBlocked):
                activation.matching_traders(
                    [{"pid":34140, "command":f"python {foreign}"}], root
                )

    def test_only_manifest_version_approved(self):
        with TemporaryDirectory() as temp:
            root=Path(temp)
            proc=process(root)
            self.assertEqual(activation.validate_target(snapshot(), [proc], root)["pid"],34140)
            s=snapshot()
            s["active_manifest_files"]["trader"]="momentum_trader_v1_9_zpta_shadow.py"
            with self.assertRaises(activation.ActivationBlocked):
                activation.validate_target(s,[proc],root)

    def test_duplicate_trader_process_blocks_activation(self):
        with TemporaryDirectory() as temp:
            root=Path(temp)
            with self.assertRaises(activation.ActivationBlocked):
                activation.validate_target(snapshot(), [process(root),process(root,34200)],root)

    def test_running_review_blocks_activation(self):
        with TemporaryDirectory() as temp:
            root=Path(temp)
            s=snapshot()
            s["tasks"][0]["state"]="Running"
            with self.assertRaises(activation.ActivationBlocked):
                activation.assert_review_idle(s,root)

    def test_stale_review_running_lock_still_blocks_maintenance(self):
        import json
        with TemporaryDirectory() as temp:
            root=Path(temp)
            (root/"post_close_review_state.json").write_text(json.dumps({
                "review_date":"2026-10-16","status":"RUNNING",
            }))
            with self.assertRaises(activation.ActivationBlocked):
                activation.assert_review_idle(snapshot(),root)

    def test_stopped_other_component_detected_without_restarting_it(self):
        s=snapshot()
        other=snapshot()
        other["components"]["dashboard"]["process"]["pids"]=[55555]
        self.assertEqual(activation.confirm_unchanged(
            s,other,("supervisor","deployment_agent","geo_feed","dashboard")
        ),["dashboard"])


class ActivationExecutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.baseline=snapshot()
        self.crypto=snapshot()
        self.old=process(self.root)
        self.after=snapshot(trader_pid=67890)
        self.after["components"]["trader"]["script_version"]["state"]="MATCHED"

    def test_default_mode_is_preflight_only_and_does_not_kill(self):
        with patch.object(activation,"inspect_host",return_value=(self.baseline,self.crypto,self.old,self.old,"a"*40)), \
             patch("subprocess.run") as run, \
             patch.object(activation,"record_receipt") as receipt:
            result=activation.activate(self.root, apply=False)
        self.assertEqual(result["status"],"VALIDATED_NO_CHANGE")
        run.assert_not_called()
        receipt.assert_not_called()

    def test_apply_only_terminates_one_trader_pid_and_leaves_other_services(self):
        from unittest.mock import Mock
        replacement=process(self.root,pid=67890)
        with patch.object(activation,"inspect_host",return_value=(self.baseline,self.crypto,self.old,self.old,"a"*40)), \
             patch.object(activation,"run_readonly",return_value=""), \
             patch.object(activation,"outside_active_hours",return_value=True), \
             patch.object(activation,"remote_matches_head",return_value="a"*40), \
             patch.object(activation,"collect",side_effect=[self.baseline,self.after,self.crypto]), \
             patch.object(activation,"windows_processes",side_effect=[[self.old],[replacement]]), \
             patch.object(activation,"record_receipt") as receipt, \
             patch.object(activation,"confirm_unchanged",return_value=[]), \
             patch.object(activation.time,"sleep"), \
             patch("subprocess.run",return_value=SimpleNamespace(returncode=0)) as run:
            result=activation.activate(self.root,apply=True,stable_seconds=0)
        self.assertEqual(result["status"],"PAPER_TRADER_RESTART_OBSERVED")
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0],["taskkill","/PID","34140","/F"])
        self.assertFalse("CryptoTracker" in str(run.call_args))
        self.assertFalse(result["release_verified"])
        self.assertTrue(receipt.called)

    def test_failed_stop_refuses_any_additional_process_changes(self):
        with patch.object(activation,"inspect_host",return_value=(self.baseline,self.crypto,self.old,self.old,"a"*40)), \
             patch.object(activation,"run_readonly",return_value=""), \
             patch.object(activation,"outside_active_hours",return_value=True), \
             patch.object(activation,"remote_matches_head",return_value="a"*40), \
             patch.object(activation,"collect",return_value=self.baseline), \
             patch.object(activation,"windows_processes",return_value=[self.old]), \
             patch.object(activation,"record_receipt"), \
             patch("subprocess.run",return_value=SimpleNamespace(returncode=1)) as run:
            with self.assertRaisesRegex(activation.ActivationBlocked,"could not be stopped"):
                activation.activate(self.root,apply=True)
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0][0],"taskkill")


if __name__ == "__main__":
    unittest.main()
