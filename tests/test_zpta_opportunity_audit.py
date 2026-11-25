import copy
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from research.zpta_opportunity_audit import capture, resolve, report, liquidity_counterfactual, stamp


class OpportunityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "research.sqlite3"
        self.time = datetime(2026, 11, 24, 15, tzinfo=timezone.utc)
        self.args = dict(
            bar={"ts": self.time.isoformat(), "open": 1., "high": 1.1, "low": .9, "close": 1., "volume": 0.},
            received_at=(self.time + timedelta(minutes=16)).isoformat(), provider="yahoo_delayed",
            features={"session_return": -.1, "ret_3m": .01, "dollar_volume_5m": 0.,
                      "vwap_gap": .01, "ret_5m": .02, "spread_proxy_pct": .09, "trade_bars_5m": 1.},
            regime="LIQUIDITY_DANGER", scores=[], ensemble=40.,
            limits={"min_dollar_volume": 25000., "max_spread": .08, "entry_score": 68.,
                    "max_trades": 6, "daily_loss_dollars": 30.},
            context={"entry_cutoff": True, "trades_today": 6, "realized_today": -30.,
                     "position_open": True, "cash": 0., "price": 1.}, source_identity={"test": True})

    def test_all_reasons_and_feed_quality_preserved(self):
        capture(self.path, **self.args)
        out = report(self.path)
        self.assertEqual(len(out["blocked_reasons"]), 10)
        self.assertEqual(out["quality_counts"]["DELAYED_REFERENCE"], 1)
        self.assertEqual(out["verified_fills"], 0)

    def test_first_receipt_duplicate_and_revision(self):
        capture(self.path, **self.args)
        changed = copy.deepcopy(self.args)
        changed["received_at"] = (self.time + timedelta(minutes=17)).isoformat()
        capture(self.path, **changed)
        changed["bar"]["volume"] = 10
        capture(self.path, **changed)
        capture(self.path, **changed)
        out = report(self.path)
        self.assertEqual(out["opportunities"], 1)
        self.assertEqual(out["revisions"], 1)
        self.assertEqual(out["last_received_at"], self.args["received_at"])

    def test_concurrent_capture_has_single_original(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: capture(self.path, **self.args), range(8)))
        self.assertEqual(report(self.path)["opportunities"], 1)

    def test_outcomes_start_after_receipt_and_are_idempotent(self):
        capture(self.path, **self.args)
        # Historical bar at signal+5m is already known at receipt and cannot score it.
        early = {**self.args["bar"], "ts": (self.time + timedelta(minutes=5)).isoformat(), "close": 2.}
        future = {**self.args["bar"], "ts": (self.time + timedelta(minutes=20)).isoformat(), "close": 1.1}
        now = (self.time + timedelta(minutes=21)).isoformat()
        self.assertEqual(resolve(self.path, [early], now), 0)
        self.assertEqual(resolve(self.path, [future], now), 1)
        self.assertEqual(resolve(self.path, [future], now), 0)
        with closing(sqlite3.connect(self.path)) as db:
            result = json.loads(db.execute("SELECT record_json FROM outcomes").fetchone()[0])
        self.assertAlmostEqual(result["print_return_pct"], 10.)
        self.assertIsNone(result["executable_return_pct"])

    def test_missing_or_future_or_different_provider_outcomes_not_substituted(self):
        capture(self.path, **self.args)
        distant = {**self.args["bar"], "ts": (self.time + timedelta(minutes=25)).isoformat()}
        self.assertEqual(resolve(self.path, [distant], (self.time + timedelta(minutes=26)).isoformat()), 0)
        not_known = {**self.args["bar"], "ts": (self.time + timedelta(minutes=20)).isoformat()}
        self.assertEqual(resolve(self.path, [not_known], (self.time + timedelta(minutes=20)).isoformat()), 0)
        not_known["provider"] = "other"
        self.assertEqual(resolve(self.path, [not_known], (self.time + timedelta(minutes=21)).isoformat()), 0)

    def test_uncompleted_bar_naive_time_and_nan_rejected(self):
        with self.assertRaises(ValueError):
            stamp("2026-11-24T15:00:00")
        for change in ({"received_at": self.time.isoformat()},
                       {"bar": {**self.args["bar"], "close": float("nan")}}):
            with self.assertRaises(ValueError):
                capture(self.path, **{**self.args, **change})

    def test_counterfactual_does_not_invent_fills(self):
        result = liquidity_counterfactual([self.args])
        self.assertEqual(result["10000"]["verified_fills"], 0)
        self.assertIsNone(result["10000"]["net_executable_return_pct"])


if __name__ == "__main__":
    unittest.main()
