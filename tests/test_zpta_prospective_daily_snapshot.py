"""Prospective daily snapshot must never use a future bar or claim fills."""
import unittest
from datetime import date, timedelta
from analysis.zpta_prospective_daily_snapshot import make_snapshot


def sample():
    start = date(2026, 10, 12)
    days = []
    d = start
    while len(days) < 11:
        if d.weekday() < 5:
            days.append(d.isoformat())
        d += timedelta(days=1)
    rows = [{"date": day, "open": .75, "high": .8022,
             "low": .70, "close": .75, "volume": 100000} for day in days]
    rows[-4]["close"] = .74
    rows[-3]["close"] = .72
    rows[-2]["close"] = .75
    rows[-1].update({"open": .75, "high": .75, "low": .631,
                     "close": .72, "volume": 279654})
    return rows


def snapshot(rows=None, **kwargs):
    params = {"as_of": "2026-10-26", "retrieved_utc": "2026-10-26T21:00:00+00:00",
              "source": "test-source"}
    params.update(kwargs)
    return make_snapshot(rows if rows is not None else sample(), **params)


class ProspectiveSnapshotTests(unittest.TestCase):
    def test_oct26_one_rule_and_no_trade(self):
        s = snapshot()
        self.assertEqual(s["snapshot_type"], "SAME_DAY_POST_CLOSE_CANDIDATE")
        self.assertEqual(s["completed_day_signal_flags"],
                         ["down_day_10pct_below_prior_ten_day_high"])
        self.assertTrue(s["research_liquidity_gate_pass"])
        self.assertTrue(s["research_candidate"])
        self.assertAlmostEqual(s["features"]["close_change_pct"], -4.0)
        self.assertAlmostEqual(s["features"]["rsi3"], 37.5)
        self.assertEqual(s["future_outcomes"], {"1d": None, "3d": None, "5d": None})
        self.assertFalse(s["real_money_trading_allowed"])
        self.assertFalse(s["independent_price_volume_reconciliation_verified"])

    def test_stale_source_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "STALE_OR_FUTURE_SOURCE"):
            snapshot(sample()[:-1])

    def test_future_bar_fails_closed(self):
        bars = sample()
        bars.append({**bars[-1], "date": "2026-10-27"})
        with self.assertRaisesRegex(ValueError, "STALE_OR_FUTURE_SOURCE"):
            snapshot(bars)

    def test_pre_close_retrieval_fails(self):
        with self.assertRaisesRegex(ValueError, "settlement"):
            snapshot(retrieved_utc="2026-10-26T19:00:00+00:00")

    def test_naive_retrieval_fails(self):
        with self.assertRaisesRegex(ValueError, "timezone"):
            snapshot(retrieved_utc="2026-10-26T21:00:00")

    def test_late_snapshot_marked_historical_replay(self):
        s = snapshot(retrieved_utc="2026-10-27T21:00:00+00:00")
        self.assertEqual(s["snapshot_type"], "HISTORICAL_REPLAY_NOT_PROSPECTIVE")

    def test_no_volume_blocks_research_candidate(self):
        bars = sample()
        bars[-1]["volume"] = 0
        s = snapshot(bars)
        self.assertFalse(s["research_candidate"])
        self.assertEqual(s["candidate_status"], "NO_QUALIFYING_RESEARCH_ENTRY")

    def test_no_signal_is_not_a_buy(self):
        bars = sample()
        bars[-1]["close"] = .75
        s = snapshot(bars)
        self.assertEqual(s["completed_day_signal_flags"], [])
        self.assertFalse(s["research_candidate"])

    def test_metadata_date_must_match(self):
        with self.assertRaisesRegex(ValueError, "Metadata"):
            snapshot(provider_last_date="2026-10-23")

    def test_reject_duplicate_dates(self):
        bars = sample()
        bars[-2]["date"] = bars[-3]["date"]
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            snapshot(bars)

    def test_input_hash_changes_on_revision(self):
        bars = sample()
        a = snapshot(bars)
        bars[-1]["volume"] += 1
        b = snapshot(bars)
        self.assertNotEqual(a["input_ohlcv_sha256"], b["input_ohlcv_sha256"])


if __name__ == "__main__":
    unittest.main()
