"""Real but isolated Windows process-discovery integration test.

Spawns exactly one temporary harmless sleeper and cleans it up by handle;
never touches the user's trader, scheduled tasks, or services.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import unittest

from infrastructure.runtime_inventory import windows_processes, windows_tasks, associate_process


@unittest.skipUnless(os.name == "nt", "Windows process integration only")
class WindowsDiscoveryIntegration(unittest.TestCase):
    def test_spawned_dummy_is_discovered_and_no_other_pid_is_manipulated(self):
        with TemporaryDirectory() as temp:
            worker = Path(temp) / "infrastructure_dummy_worker.py"
            worker.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
            proc = subprocess.Popen(
                [sys.executable, str(worker)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            try:
                observed = None
                for _ in range(12):
                    found = [p for p in windows_processes() if int(p.get("pid") or 0) == proc.pid]
                    if found:
                        observed = found[0]
                        break
                    time.sleep(0.5)
                self.assertIsNotNone(observed, "Controlled dummy process not returned by Windows CIM")
                component = {
                    "role": "service", "script_pattern": "infrastructure_dummy_worker.py"
                }
                matched = associate_process(component, [observed], {})
                if observed.get("command"):
                    self.assertEqual(matched["state"], "OBSERVED")
                    self.assertEqual(matched["pids"], [proc.pid])
                else:
                    self.assertEqual(matched["state"], "UNKNOWN")
            finally:
                # Only stop the child process created by this test.
                if proc.poll() is None:
                    proc.terminate()
                proc.wait(timeout=15)

    def test_nonexistent_task_is_reported_missing_without_creation(self):
        tasks = windows_tasks(["Infrastructure Registry Dummy Task - Do Not Create"])
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["state"], "MISSING")


if __name__ == "__main__":
    unittest.main()
