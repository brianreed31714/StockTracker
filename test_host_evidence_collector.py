import tempfile
import unittest
from pathlib import Path
from infrastructure.host_evidence_collector import collect_host_evidence

class CollectorTests(unittest.TestCase):
    def test_fail_closed_without_process(self):
        with tempfile.TemporaryDirectory() as d:
            r = collect_host_evidence(Path(d), {}, dependencies=())
            self.assertFalse(r["loaded_code_verified"])
            self.assertIsNone(r["disk_code_sha256"])

    def test_disk_hash_never_claims_loaded_memory(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "trader.py").write_text("print('paper')", encoding="utf-8")
            (root / "dep.py").write_text("x=1", encoding="utf-8")
            snapshot = {"components": {"trader": {"process": {
                "state": "OBSERVED", "script": "trader.py"}}}}
            r = collect_host_evidence(root, snapshot, dependencies=("dep.py",))
            self.assertEqual(len(r["disk_code_sha256"]), 64)
            self.assertEqual(len(r["disk_dependencies_sha256"]), 64)
            self.assertFalse(r["loaded_code_verified"])
            self.assertFalse(r["loaded_dependencies_verified"])

if __name__ == "__main__":
    unittest.main()
