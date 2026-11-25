"""Offline existing-entrypoint tests: isolated state and all network blocked."""
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
import gc
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import zpta_specialist_v0_1 as specialist


class RuntimeCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.start = datetime(2026, 11, 24, 14, 30, tzinfo=timezone.utc)
        self.now = self.start + timedelta(minutes=30)
        self.bars = [specialist.Bar(self.start + timedelta(minutes=i), 1., 1.01, .99, 1., 0.) for i in range(25)]
        self.stack = ExitStack()
        for key, value in {"DB_PATH": self.root / "paper.sqlite3", "LOG_ROOT": self.root / "logs",
                           "STATE_PATH": self.root / "state.json", "PUSHOVER_ENABLED": False}.items():
            self.stack.enter_context(patch.object(specialist, key, value))
        self.stack.enter_context(patch.object(specialist, "utc_now", lambda: self.now))
        self.stack.enter_context(patch.object(specialist, "market_now", lambda: self.now.astimezone(specialist.MARKET_TZ)))
        self.stack.enter_context(patch.object(specialist, "fetch_bars", lambda: (self.bars, "yahoo_delayed")))
        self.stack.enter_context(patch.object(specialist, "cached_asset_preflight", lambda: {"available": False}))
        self.stack.enter_context(patch("requests.sessions.Session.request", side_effect=AssertionError("NETWORK FORBIDDEN")))
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.stack.close()
        # Legacy specialist context managers commit but rely on GC for close.
        gc.collect()
        self.temp.cleanup()

    def test_real_entrypoint_captures_and_deduplicates_without_trade(self):
        first = specialist.run_once()
        second = specialist.run_once()
        self.assertEqual(first["status"], "OK")
        self.assertEqual(second["status"], "NO_NEW_BAR")
        self.assertEqual(second["research"]["opportunities"], 1)
        self.assertEqual(specialist.trades_today(), 0)
        data = json.loads((specialist.LOG_ROOT / "research_latest.json").read_text())
        self.assertTrue(data["paper_only"])
        self.assertEqual(data["runtime_identity"]["source_hashes_at_import"].keys(),
                         {"zpta_specialist_v0_1.py", "zpta_research_runtime.py", "research/zpta_opportunity_audit.py"})
        self.assertTrue(data["blocked_reasons"]["LIQUIDITY_DANGER"])

    def test_observer_failure_prevents_unlogged_new_entry(self):
        with patch.object(specialist.zpta_research_runtime, "observe", side_effect=OSError("disk full")), \
                patch.object(specialist, "maybe_trade") as trade:
            out = specialist.run_once()
            self.assertEqual(out["status"], "RESEARCH_AUDIT_ERROR")
            trade.assert_not_called()

    def test_predictions_are_created_before_due_and_remain_print_references(self):
        specialist.run_once()
        import sqlite3
        from contextlib import closing
        with closing(sqlite3.connect(specialist.DB_PATH)) as db:
            rows = db.execute("SELECT created_ts,due_ts,reason FROM zpta_predictions").fetchall()
        self.assertEqual(len(rows), 12)
        for created, due, reason in rows:
            self.assertLess(datetime.fromisoformat(created), datetime.fromisoformat(due))
            self.assertIn("PRINT_REFERENCE_NOT_FILL", reason)

    def test_observer_failure_preserves_existing_position_exit_evaluation(self):
        specialist.save_state({"cash": 850., "position": {"id": "existing"}})
        with patch.object(specialist.zpta_research_runtime, "observe", side_effect=OSError("disk full")), \
                patch.object(specialist, "maybe_trade", return_value="HOLD") as trade:
            # Keep the rest of the accounting isolated from the synthetic position.
            with patch.object(specialist, "write_daily_summary"), patch.object(specialist, "get_state", return_value={
                    "cash": 850., "position": {"id": "existing", "qty": 150.}, "last_bar_ts": None}):
                result = specialist.run_once()
            trade.assert_called_once()
            self.assertEqual(result["research"]["status"], "RESEARCH_AUDIT_ERROR")


if __name__ == "__main__":
    unittest.main()
