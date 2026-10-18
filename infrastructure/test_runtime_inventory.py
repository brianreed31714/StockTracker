"""Non-destructive process identity and host-evidence regression tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from infrastructure.runtime_inventory import associate_process, latest_launches, report_health


BASE = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
SMART = {
    "id": "smart_money",
    "role": "observer",
    "script_pattern": "smart_money_monitor_*.py",
    "health": {
        "type": "json_heartbeat",
        "artifact": "SmartMoneyMonitor/data/smart_money_feed_health_v23.json",
        "max_age_seconds": 360,
        "success_status": "OK",
    },
}


class RuntimeInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def make_health(self, **updates):
        report = {
            "observed_at_utc": (BASE - timedelta(seconds=60)).isoformat(),
            "cycle_number": 3,
            "tracked_wallets": 4,
            "successful_wallet_checks": 4,
            "failed_wallet_checks": 0,
            "status": "OK",
        }
        report.update(updates)
        path = self.root / SMART["health"]["artifact"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report), encoding="utf-8")
        return path

    def test_recent_success_is_health_evidence(self):
        self.make_health()
        self.assertEqual(report_health(self.root, SMART, now=BASE)["state"], "HEALTHY")

    def test_missing_report_is_not_healthy(self):
        self.assertEqual(report_health(self.root, SMART, now=BASE)["state"], "MISSING")

    def test_degraded_wallet_is_not_healthy(self):
        self.make_health(successful_wallet_checks=3, failed_wallet_checks=1, status="DEGRADED")
        self.assertEqual(report_health(self.root, SMART, now=BASE)["state"], "DEGRADED")

    def test_stale_ok_is_not_healthy(self):
        self.make_health(observed_at_utc=(BASE - timedelta(minutes=10)).isoformat())
        self.assertEqual(report_health(self.root, SMART, now=BASE)["state"], "STALE")

    def test_inconsistent_ok_is_not_healthy(self):
        self.make_health(successful_wallet_checks=3, failed_wallet_checks=1)
        self.assertEqual(report_health(self.root, SMART, now=BASE)["state"], "INCONSISTENT")

    def test_invisible_command_line_verified_via_log_and_start(self):
        # Use local wall-clock timestamp because supervisor.log writes local time.
        wall = datetime(2026, 10, 18, 10, 50, 24)
        start = wall.astimezone(timezone.utc).isoformat()
        proc = {"pid": 3096, "command": "", "started_utc": start}
        log = {3096: {"time": wall.isoformat(),
                      "script": "SmartMoneyMonitor/smart_money_monitor_v2_3_feed_health_audit.py"}}
        result = associate_process(SMART, [proc], log)
        self.assertEqual(result["state"], "OBSERVED")
        self.assertEqual(result["identification"], "supervisor_log_verified_start")
        self.assertNotIn("command", result)

    def test_pid_reuse_not_misattributed(self):
        wall = datetime(2026, 10, 18, 10, 50, 24)
        proc = {"pid": 3096, "command": "",
                "started_utc": (wall.astimezone(timezone.utc) + timedelta(hours=7)).isoformat()}
        log = {3096: {"time": wall.isoformat(),
                      "script": "SmartMoneyMonitor/smart_money_monitor_v2_3_feed_health_audit.py"}}
        self.assertEqual(associate_process(SMART, [proc], log)["state"], "UNKNOWN")

    def test_hidden_unattributed_process_not_guessed(self):
        proc = {"pid": 10, "command": "", "started_utc": BASE.isoformat()}
        self.assertEqual(associate_process(SMART, [proc], {})["state"], "UNKNOWN")

    def test_foreign_project_process_is_not_smart_money(self):
        proc = {"pid": 77, "command": "python momentum_trader_v1_10_runtime_audit.py",
                "started_utc": BASE.isoformat()}
        self.assertEqual(associate_process(SMART, [proc], {})["state"], "UNKNOWN")

    def test_command_line_identified_without_leaking_command(self):
        proc = {"pid": 31, "command": r"C:\Python313\python.exe C:\Private\SmartMoneyMonitor\smart_money_monitor_v2_3_feed_health_audit.py --secret=x",
                "started_utc": BASE.isoformat()}
        result = associate_process(SMART, [proc], {})
        self.assertEqual(result["state"], "OBSERVED")
        self.assertEqual(result["identification"], "command_line")
        self.assertNotIn("secret", json.dumps(result))

    def test_duplicate_processes_are_detected(self):
        procs = [{"pid": n, "command": "python smart_money_monitor_v2_3_feed_health_audit.py",
                  "started_utc": BASE.isoformat()} for n in (11, 12)]
        self.assertEqual(associate_process(SMART, procs, {})["state"], "DUPLICATE")

    def test_backup_filename_not_mistaken_for_process(self):
        proc = {"pid": 14, "command": "python smart_money_monitor_v2_3_feed_health_audit.py.backup"}
        self.assertEqual(associate_process(SMART, [proc], {})["state"], "UNKNOWN")

    def test_only_exact_supervisor_launch_record_is_accepted(self):
        path = self.root / "supervisor.log"
        path.write_text(
            "2026-10-18T10:50:24 | Started Smart Money: SmartMoneyMonitor/smart_money_monitor_v2_3_feed_health_audit.py pid=3096\n"
            "2026-10-18T10:50:25 | Started Trader: auto_trader_with_alerts_v11_10_research_fairness.py pid=1234\n")
        launches = latest_launches(path)
        self.assertEqual(launches[3096]["script"], "SmartMoneyMonitor/smart_money_monitor_v2_3_feed_health_audit.py")
        self.assertNotIn(43708, launches)


if __name__ == "__main__":
    unittest.main()
