import unittest
import tempfile
from pathlib import Path
from analysis.zpta_entry_volume_validation import evaluate, summarize, read_daily, bootstrap_rate_diff

class EntryVolumeTests(unittest.TestCase):
    def test_next_open_entry_differs_from_close_to_close(self):
        closes=[10,9,8,9,8]
        bars=[{"date":f"2026-10-{i+1:02d}","close":c,"open":(8.8 if i==3 else c),"volume":100+i*10} for i,c in enumerate(closes)]
        events=evaluate(bars)
        signal=next(e for e in events if e["streak"]==2)
        self.assertAlmostEqual(signal["next_close_vs_signal_close_pct"],12.5)
        self.assertAlmostEqual(signal["next_open_to_close_pct"],100*(9/8.8-1))
        self.assertEqual(summarize(events)["exact_2"]["count"],1)

    def test_iso_and_yahoo_dates(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bars.csv"
            p.write_text("Date,Open,High,Low,Close,Adj Close,Volume\\n2026-10-01,1,1,1,1,1,100\\nOct 2, 2026,1,1,1,1,1,100\\n")
            # Comma-containing human dates must be CSV-quoted.
            p.write_text('Date,Open,High,Low,Close,Adj Close,Volume\\n2026-10-01,1,1,1,1,1,100\\n"Oct 2, 2026",1,1,1,1,1,100\\n')
            self.assertEqual([x["date"] for x in read_daily(p)], ["2026-10-01", "2026-10-02"])

    def test_bootstrap_no_two_down_events(self):
        events = [{"date": f"2026-10-{i+1:02d}", "streak": 0, "next_close_vs_signal_close_pct": 1} for i in range(28)]
        self.assertIsNone(bootstrap_rate_diff(events))

if __name__=="__main__":
    unittest.main()
