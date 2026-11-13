"""活动时段记录测试。"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, time as dtime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sitguard.daylog import ActivityTracker  # noqa: E402


class TestActivityTracker(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "activity.json"
        self.now = 1_700_000_000.0
        self.tracker = ActivityTracker(self.path, clock=lambda: self.now)

    def tearDown(self):
        self.tmp.cleanup()

    def test_totals(self):
        t = self.tracker
        t.update("sitting", self.now)
        self.now += 600
        t.update("standing", self.now)
        self.now += 300
        t.update("away", self.now)
        self.now += 120
        totals = t.totals_for(datetime.fromtimestamp(self.now).date().isoformat(), self.now)
        self.assertAlmostEqual(totals["sitting"], 600, delta=1)
        self.assertAlmostEqual(totals["standing"], 300, delta=1)
        self.assertAlmostEqual(totals["away"], 120, delta=1)

    def test_save_and_reload(self):
        t = self.tracker
        t.update("sitting", self.now)
        self.now += 300
        t.save()
        reloaded = ActivityTracker(self.path, clock=lambda: self.now)
        key = datetime.fromtimestamp(self.now).date().isoformat()
        totals = reloaded.totals_for(key, self.now)
        self.assertGreaterEqual(totals["sitting"], 300)

    def test_midnight_split(self):
        day = datetime(2026, 1, 1, 23, 59, 0)
        start = day.timestamp()
        self.now = start
        self.tracker.update("sitting", start)
        self.now = start + 180
        self.tracker.update("standing", self.now)
        key1 = "2026-01-01"
        key2 = "2026-01-02"
        s1 = sum(e - s for s, e, k in self.tracker.segments_for(key1, self.now) if k == "sitting")
        s2 = sum(e - s for s, e, k in self.tracker.segments_for(key2, self.now) if k == "sitting")
        self.assertGreater(s1, 0)
        self.assertGreater(s2, 0)
        self.assertAlmostEqual(s1 + s2, 180, delta=1)

    def test_persisted_shape(self):
        self.tracker.update("sitting", self.now)
        self.now += 60
        self.tracker.save()
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(raw["version"], 1)
        self.assertTrue(raw["days"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
