import unittest
from analysis.zpta_entry_volume_validation import evaluate, summarize

class EntryVolumeTests(unittest.TestCase):
    def test_next_open_entry_differs_from_close_to_close(self):
        closes=[10,9,8,9,8]
        bars=[{"date":f"2026-10-{i+1:02d}","close":c,"open":(8.8 if i==3 else c),"volume":100+i*10} for i,c in enumerate(closes)]
        events=evaluate(bars)
        signal=next(e for e in events if e["streak"]==2)
        self.assertAlmostEqual(signal["next_close_vs_signal_close_pct"],12.5)
        self.assertAlmostEqual(signal["next_open_to_close_pct"],100*(9/8.8-1))
        self.assertEqual(summarize(events)["exact_2"]["count"],1)

if __name__=="__main__":
    unittest.main()
