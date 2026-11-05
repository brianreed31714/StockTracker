import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from analysis.zpta_quantum_headline_join import join, summarize

class NewsJoinTests(unittest.TestCase):
    def test_future_news_does_not_leak(self):
        ny=ZoneInfo("America/New_York")
        rows=[{"date":"2026-11-03","down_streak":2,"next_noon_vs_signal_close_pct":2.0,"next_eod_vs_signal_close_pct":3.0}]
        news=[{"published":datetime(2026,11,3,15,0,tzinfo=ny),"scope":"sector","sentiment":"positive","url":"a"},
              {"published":datetime(2026,11,3,17,0,tzinfo=ny),"scope":"zpta","sentiment":"negative","url":"b"}]
        result=join(rows,news)
        self.assertEqual(result[0]["sector_sentiment_score"],1)
        self.assertEqual(result[0]["zpta_sentiment_score"],0)
        self.assertIn("down_2_sector_positive",summarize(result))
        self.assertNotIn("b",result[0]["news_urls"])

if __name__=="__main__":
    unittest.main()
