"""Only future completed sessions may resolve frozen daily predictions."""
import unittest
from analysis.zpta_prospective_daily_snapshot import make_snapshot
from analysis.zpta_prospective_outcome_score import score_snapshot
from datetime import date, timedelta


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


def frozen():
    return make_snapshot(
        sample(), as_of="2026-10-26",
        retrieved_utc="2026-10-26T21:00:00+00:00",
        source="Yahoo Finance chart public delayed research endpoint")


def future(day, close, low=None):
    return {"date": day, "open": close, "high": close*1.05,
            "low": low if low is not None else close*.95,
            "close": close, "volume": 100000}


class ForwardOutcomeTests(unittest.TestCase):
    def test_no_future_outcomes_on_signal_day(self):
        result = score_snapshot(frozen(), sample())
        self.assertEqual(result["future_outcomes"],
                         {"1d": None, "3d": None, "5d": None})
        self.assertFalse(result["fully_resolved"])

    def test_one_day_score_after_future_close_only(self):
        rows = sample() + [future("2026-10-27", .75)]
        r = score_snapshot(frozen(), rows)
        self.assertIsNotNone(r["future_outcomes"]["1d"])
        self.assertIsNone(r["future_outcomes"]["3d"])
        self.assertIsNone(r["future_outcomes"]["5d"])
        self.assertFalse(r["future_outcomes"]["1d"]["broker_fill_verified"])

    def test_five_day_score_requires_five_later_bars(self):
        rows = sample() + [future("2026-10-27", .73),
                           future("2026-10-28", .75),
                           future("2026-10-29", .76),
                           future("2026-10-30", .78),
                           future("2026-11-02", .80)]
        r = score_snapshot(frozen(), rows)
        self.assertTrue(r["fully_resolved"])
        self.assertEqual(r["future_outcomes"]["5d"]["exit_session"], "2026-11-02")

    def test_revised_signal_volume_blocks_scoring(self):
        rows = sample()
        rows[-1]["volume"] += 1
        with self.assertRaisesRegex(ValueError, "REVISED"):
            score_snapshot(frozen(), rows)

    def test_revised_signal_price_blocks_scoring(self):
        rows = sample()
        rows[-1]["close"] = .74
        with self.assertRaisesRegex(ValueError, "REVISED"):
            score_snapshot(frozen(), rows)

    def test_nonprospective_snapshot_rejected(self):
        f = frozen()
        f["snapshot_type"] = "HISTORICAL_REPLAY_NOT_PROSPECTIVE"
        with self.assertRaisesRegex(ValueError, "contemporaneously"):
            score_snapshot(f, sample())

    def test_frozen_independent_source_mismatch_blocks_forward_scoring(self):
        rows = sample() + [future("2026-10-27", .73)]
        f = frozen()
        f["independent_source_quality_status"] = "SOURCE_MISMATCH_DO_NOT_PROMOTE"
        with self.assertRaisesRegex(ValueError, "SOURCE_MISMATCH_DO_NOT_SCORE"):
            score_snapshot(f, rows)

    def test_independent_single_date_match_still_unverified(self):
        rows = sample() + [future("2026-10-27", .73)]
        f = frozen()
        f["independent_source_quality_status"] = (
            "SINGLE_DATE_ANCHOR_WITHIN_TOLERANCE_NOT_FULLY_VERIFIED")
        result = score_snapshot(f, rows)
        self.assertFalse(result["independent_split_adjustment_verified"])
        self.assertFalse(result["real_money_trading_allowed"])
        self.assertIsNotNone(result["future_outcomes"]["1d"])

    def test_higher_cost_reduces_net(self):
        rows = sample() + [future("2026-10-27", .75)]
        a = score_snapshot(frozen(), rows, 0)["future_outcomes"]["1d"]["hypothetical_net_pct"]
        b = score_snapshot(frozen(), rows, .03)["future_outcomes"]["1d"]["hypothetical_net_pct"]
        self.assertGreater(a, b)


if __name__ == "__main__":
    unittest.main()
