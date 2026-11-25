"""Deterministic source-QA tests; never contact Yahoo or a broker."""
import unittest
from analysis.zpta_daily_history_fetch import extract_chart


def payload():
    return {
        "chart": {
            "error": None,
            "result": [{
                "meta": {"symbol": "ZPTA", "currency": "USD",
                         "exchangeTimezoneName": "America/New_York"},
                "timestamp": [1780671000, 1780757400],
                "indicators": {"quote": [{
                    "open": [0.60, 0.58], "high": [0.65, 0.60],
                    "low": [0.55, 0.51], "close": [0.58, 0.55],
                    "volume": [100000, 0],
                }]},
                "events": {"splits": {"a": {"date": 1780671000, "numerator": 1, "denominator": 2}}},
            }],
        },
    }


class DailyHistoryFetcherTests(unittest.TestCase):
    def test_parse_and_preserve_zero_volume_warning(self):
        bars, meta = extract_chart(payload())
        self.assertEqual(len(bars), 2)
        self.assertEqual(meta["zero_volume_days"], 1)
        self.assertEqual(len(meta["split_events"]), 1)
        self.assertFalse(meta["corporate_action_adjustment_independently_verified"])

    def test_reject_wrong_ticker(self):
        p = payload()
        p["chart"]["result"][0]["meta"]["symbol"] = "TSLA"
        with self.assertRaises(ValueError):
            extract_chart(p)

    def test_reject_missing_ohlcv(self):
        p = payload()
        p["chart"]["result"][0]["indicators"]["quote"][0]["low"] = [0.55]
        with self.assertRaises(ValueError):
            extract_chart(p)

    def test_reject_bad_price_order(self):
        p = payload()
        p["chart"]["result"][0]["indicators"]["quote"][0]["high"][0] = 0.54
        with self.assertRaises(ValueError):
            extract_chart(p)

    def test_reject_duplicate_local_date(self):
        p = payload()
        p["chart"]["result"][0]["timestamp"][1] = p["chart"]["result"][0]["timestamp"][0]
        with self.assertRaises(ValueError):
            extract_chart(p)

    def test_missing_bar_is_reported_not_fabricated(self):
        p = payload()
        p["chart"]["result"][0]["indicators"]["quote"][0]["volume"][0] = None
        bars, meta = extract_chart(p)
        self.assertEqual(len(bars), 1)
        self.assertEqual(meta["missing_rows"], 1)


if __name__ == "__main__":
    unittest.main()
