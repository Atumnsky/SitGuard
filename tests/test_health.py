"""画面健康检测（雪花）测试。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sitguard.health import FrameHealth  # noqa: E402


class TestFrameHealth(unittest.TestCase):
    def test_snow_detected(self):
        health = FrameHealth(snow_seconds=1.0)
        rng = np.random.default_rng(7)
        now = 0.0
        fired = False
        for _ in range(25):
            frame = rng.integers(0, 256, (360, 640, 3), dtype=np.uint8)
            now += 0.1
            fired = health.update(frame, now) or fired
        self.assertTrue(fired)

    def test_normal_scene_not_snow(self):
        health = FrameHealth(snow_seconds=0.5)
        yy, xx = np.mgrid[0:360, 0:640]
        frame = np.stack([
            ((xx // 8) % 256),
            ((yy // 8) % 256),
            (((xx + yy) // 16) % 256),
        ], axis=2).astype(np.uint8)
        now = 0.0
        for _ in range(10):
            now += 0.1
            self.assertFalse(health.update(frame, now))

    def test_black_detected_after_timeout(self):
        health = FrameHealth(snow_seconds=1.0, black_seconds=1.0)
        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        now = 0.0
        result = None
        for _ in range(15):
            now += 0.1
            result = health.update(frame, now) or result
        self.assertEqual(result, "black")

    def test_black_frame_is_not_snow(self):
        health = FrameHealth(snow_seconds=0.5)
        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        now = 0.0
        for _ in range(10):
            now += 0.1
            self.assertFalse(health.update(frame, now))


if __name__ == "__main__":
    unittest.main(verbosity=2)
