"""Offline deterministic tests for venue-regime-separated ZPTA swing analysis."""
import unittest
from datetime import date, timedelta

from analysis.zpta_market_regime_audit import audit_regimes, venue_regime, REGIMES


def bars(first="2026-06-01", n=35, volume=100000):
    d = date.fromisoformat(first)
    rows = []
    close = 1.0
    for i in range(n):
        old = close
        close *= .93 if i in (11, 12, 19, 20) else 1.01
        rows.append({
            "date": (d + timedelta(days=i)).isoformat(),
            "open": old, "high": max(old, close)*1.02,
            "low": min(old, close)*.98, "close": close, "volume": volume
        })
    return rows


class MarketRegimeAuditTests(unittest.TestCase):
    def test_issuer_boundaries(self):
        self.assertEqual(venue_regime("2025-12-14"), REGIMES[0])
        self.assertEqual(venue_regime("2025-12-15"), REGIMES[1])
        self.assertEqual(venue_regime("2026-06-15"), REGIMES[1])
        self.assertEqual(venue_regime("2026-06-16"), REGIMES[2])

    def test_never_promote(self):
        r = audit_regimes(bars(), as_of="2026-07-05")
        self.assertFalse(r["promotion_allowed"])
        self.assertEqual(r["sessions_analyzed"], 35)

    def test_no_future_rows_used(self):
        b = bars()
        cutoff = "2026-06-22"
        a = audit_regimes(b, as_of=cutoff)
        b[-1]["close"] = 999
        b[-1]["high"] = 999
        c = audit_regimes(b, as_of=cutoff)
        self.assertEqual(a, c)

    def test_no_cross_venue_event(self):
        r = audit_regimes(bars(), as_of="2026-07-05")
        self.assertGreater(sum(r["cross_venue_events_excluded"].values()), 0)

    def test_late_venue_is_independent(self):
        r = audit_regimes(bars(), as_of="2026-07-05")
        self.assertEqual(r["regimes"][REGIMES[0]]["liquidity"]["sessions"], 0)
        self.assertEqual(r["regimes"][REGIMES[1]]["liquidity"]["sessions"], 15)
        self.assertEqual(r["regimes"][REGIMES[2]]["liquidity"]["sessions"], 20)

    def test_zero_volume_gates_all_trades(self):
        r = audit_regimes(bars(volume=0), as_of="2026-07-05")
        for regime in REGIMES:
            self.assertEqual(
                r["regimes"][regime]["strategies"]["all_eligible_sessions"]["5d"]["independent_trades"], 0)
        self.assertFalse(r["last_signal_day_liquid"])

    def test_cost_increases_reduce_net(self):
        b = bars()
        a = audit_regimes(b, as_of="2026-07-05", one_way_cost=0)
        c = audit_regimes(b, as_of="2026-07-05", one_way_cost=.05)
        x = a["regimes"][REGIMES[2]]["strategies"]["all_eligible_sessions"]["1d"]["mean_net_pct"]
        y = c["regimes"][REGIMES[2]]["strategies"]["all_eligible_sessions"]["1d"]["mean_net_pct"]
        self.assertIsNotNone(x)
        self.assertGreater(x, y)

    def test_invalid_input(self):
        with self.assertRaises(ValueError):
            audit_regimes(bars(), one_way_cost=-.01)
        with self.assertRaises(ValueError):
            audit_regimes(bars(), as_of="2024-01-01")
        bad = bars()
        bad[5]["date"] = bad[4]["date"]
        with self.assertRaises(ValueError):
            audit_regimes(bad)

    def test_venue_and_signal_are_not_the_same(self):
        r = audit_regimes(bars(), as_of="2026-07-05")
        self.assertEqual(r["last_venue_regime"], REGIMES[2])
        self.assertIsInstance(r["last_signal_flags"], list)


if __name__ == "__main__":
    unittest.main()
