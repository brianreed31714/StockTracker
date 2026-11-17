"""Exercise the active engine's report policy without importing broker clients."""
import ast
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from dotenv import dotenv_values


class EodReportPolicyTests(unittest.TestCase):
    def test_inherited_notification_flag_cannot_override_repository(self):
        source = ast.parse((Path(__file__).parent / "momentum_trader_v1_10_runtime_audit.py").read_text(encoding="utf-8"))
        fn = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == "apply_repository_eod_policy")
        with TemporaryDirectory() as folder:
            path = Path(folder) / ".env.config"
            path.write_text("PUSHOVER_STOCK_EOD_ENABLED=0\nPUSHOVER_STOCK_EOD_HOUR=19\nPUSHOVER_STOCK_EOD_MINUTE=00\n")
            namespace = {"CONFIG_FILE": path, "dotenv_values": dotenv_values, "os": os}
            exec(compile(ast.Module(body=[fn], type_ignores=[]), "report-policy", "exec"), namespace)
            with patch.dict(os.environ, {"PUSHOVER_STOCK_EOD_ENABLED": "1", "PUSHOVER_STOCK_EOD_HOUR": "16", "BUY_SCORE_THRESHOLD": "71"}):
                namespace[fn.name]()
                self.assertEqual(os.environ["PUSHOVER_STOCK_EOD_ENABLED"], "0")
                self.assertEqual(os.environ["PUSHOVER_STOCK_EOD_HOUR"], "19")
                self.assertEqual(os.environ["PUSHOVER_STOCK_EOD_MINUTE"], "00")
                self.assertEqual(os.environ["BUY_SCORE_THRESHOLD"], "71")
                path.unlink()
                os.environ["PUSHOVER_STOCK_EOD_ENABLED"] = "1"
                namespace[fn.name]()
                self.assertEqual(os.environ["PUSHOVER_STOCK_EOD_ENABLED"], "0")


if __name__ == "__main__":
    unittest.main()
