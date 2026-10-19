"""Check Pacific reporting and activation time boundaries."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from infrastructure.activate_review_repair import outside_active_hours

PT = ZoneInfo("America/Los_Angeles")

class PacificWindowTests(unittest.TestCase):
    def test_boundaries_on_october_monday(self):
        for hh, mm, allowed in [(6,29,True),(6,30,False),(13,35,False),(13,39,False),(13,40,True)]:
            with self.subTest(time=(hh,mm)):
                self.assertEqual(outside_active_hours(datetime(2026,10,19,hh,mm,tzinfo=PT)),allowed)

    def test_boundaries_on_november_monday(self):
        for hh, mm, allowed in [(6,29,True),(6,30,False),(13,39,False),(13,40,True)]:
            with self.subTest(time=(hh,mm)):
                self.assertEqual(outside_active_hours(datetime(2026,11,2,hh,mm,tzinfo=PT)),allowed)

if __name__ == "__main__":
    unittest.main()
