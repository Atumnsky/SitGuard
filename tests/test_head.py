"""头部朝向判断测试。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sitguard.head import HeadState  # noqa: E402
from sitguard.posture import Landmark, PostureProfile  # noqa: E402


def lm(x, y, vis=1.0):
    return Landmark(x, y, vis)


def pose(nose_y=0.5, nose_x=0.5, shoulder_y=0.9, width=0.3, vis=1.0):
    p = [lm(0.5, 0.5) for _ in range(33)]
    p[0] = lm(nose_x, nose_y, vis)
    p[11] = lm(0.5 - width / 2, shoulder_y)
    p[12] = lm(0.5 + width / 2, shoulder_y)
    return p


class TestHeadState(unittest.TestCase):
    def test_face_low_is_down(self):
        h = HeadState()
        t = 0.0
        prof = PostureProfile(face_y=0.65, visible=True)
        h.update(True, prof, pose(nose_y=0.55), t, 0.65)
        low = PostureProfile(face_y=0.78, face_h=0.3, visible=True)
        self.assertEqual(h.update(True, low, pose(nose_y=0.7), t + 0.3, 0.65), "down")

    def test_pose_nose_low_is_down(self):
        h = HeadState()
        h.update(True, PostureProfile(face_y=0.65, visible=True), pose(nose_y=0.6), 0.0, 0.65)
        self.assertEqual(h.update(False, PostureProfile(visible=False),
                                  pose(nose_y=0.92), 1.0, 0.65), "down")

    def test_pose_nose_side_is_side(self):
        h = HeadState()
        h.update(True, PostureProfile(face_y=0.65, visible=True), pose(), 0.0, 0.65)
        self.assertEqual(h.update(False, PostureProfile(visible=False),
                                  pose(nose_y=0.6, nose_x=0.95), 1.0, 0.65), "side")


    def test_side_from_face_trajectory(self):
        h = HeadState()
        h.update(True, PostureProfile(face_y=0.65, face_x=0.5, visible=True),
                 pose(), 0.0, 0.65)
        h.update(True, PostureProfile(face_y=0.65, face_x=0.92, visible=True),
                 pose(), 0.5, 0.65)
        self.assertEqual(h.update(False, PostureProfile(visible=False),
                                  pose(nose_y=0.6, vis=0.1), 0.8, 0.65), "side")

    def test_slightly_lower_is_not_down(self):
        h = HeadState()
        h.update(True, PostureProfile(face_y=0.65, visible=True), pose(), 0.0, 0.65)
        self.assertIsNone(h.update(True, PostureProfile(face_y=0.72, face_h=0.2,
                                                       visible=True), pose(), 1.0, 0.65))

    def test_face_lost_at_bottom_is_down(self):
        h = HeadState()
        h.update(True, PostureProfile(face_y=0.88, face_h=0.1, visible=True),
                 pose(), 0.0, 0.65)
        self.assertEqual(h.update(False, PostureProfile(visible=False),
                                  pose(vis=0.1), 1.0, 0.65, body_present=True), "down")
    def test_normal_face_resets(self):
        h = HeadState()
        h.update(True, PostureProfile(face_y=0.65, visible=True), pose(), 0.0, 0.65)
        self.assertIsNone(h.update(True, PostureProfile(face_y=0.64, visible=True),
                                    pose(), 1.0, 0.65))


if __name__ == "__main__":
    unittest.main(verbosity=2)
