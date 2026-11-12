"""核心状态机 + 姿态分析测试（无需摄像头）。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sitguard.config import Config
from sitguard.engine import Phase, SessionEngine
from sitguard.posture import (Landmark, PostureAnalyzer, PostureProfile,
                              classify_pose)
from sitguard.presence import PresenceTracker, choose_face


class FakeClock:
    def __init__(self, start: float = 1000.0):
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> float:
        self.t += dt
        return self.t


def make_engine(**kw):
    kwargs = {"away_minutes": 5, "break_minutes": 5}
    kwargs.update(kw)
    cfg = Config(**kwargs).normalized()
    clock = FakeClock()
    eng = SessionEngine(cfg, clock=clock)
    events = []
    eng.add_listener(lambda ev: events.append((ev.kind, ev.detail)))
    return eng, clock, events


def sit(eng, clock, seconds: float, step: float = 1.0, posture: str = "sitting"):
    elapsed = 0.0
    while elapsed < seconds:
        dt = min(step, seconds - elapsed)
        clock.advance(dt)
        eng.notify_presence(True, clock())
        eng.notify_posture(posture, clock())
        eng.tick(clock())
        elapsed += dt


def leave(eng, clock, seconds: float, step: float = 1.0):
    elapsed = 0.0
    while elapsed < seconds:
        dt = min(step, seconds - elapsed)
        clock.advance(dt)
        eng.notify_presence(False, clock())
        eng.tick(clock())
        elapsed += dt


def lm(x, y, vis=1.0):
    return Landmark(x, y, vis)


def standing_pose():
    # 站直：髋 0.55、膝 0.78、踝 0.95，膝角接近 180°
    return [
        lm(0.5, 0.10), lm(0.45, 0.12), lm(0.55, 0.12), lm(0.44, 0.15),
        lm(0.56, 0.15), lm(0.42, 0.22), lm(0.58, 0.22), lm(0.40, 0.30),
        lm(0.60, 0.30), lm(0.39, 0.38), lm(0.61, 0.38), lm(0.40, 0.28),
        lm(0.60, 0.28),
        lm(0.38, 0.40), lm(0.62, 0.40), lm(0.37, 0.50), lm(0.63, 0.50),
        lm(0.36, 0.60), lm(0.64, 0.60), lm(0.36, 0.70), lm(0.64, 0.70),
        lm(0.36, 0.78), lm(0.64, 0.78),
        lm(0.42, 0.55), lm(0.58, 0.55),      # hips
        lm(0.42, 0.78), lm(0.58, 0.78),      # knees
        lm(0.42, 0.95), lm(0.58, 0.95),      # ankles
        lm(0.42, 0.98), lm(0.58, 0.98),
        lm(0.42, 0.99), lm(0.58, 0.99),
    ]


def sitting_pose():
    p = standing_pose()
    # 坐姿：膝盖前伸、脚踝回收，膝角约 90–100°
    p[23] = lm(0.42, 0.60)
    p[24] = lm(0.58, 0.60)
    p[25] = lm(0.60, 0.72)
    p[26] = lm(0.70, 0.72)
    p[27] = lm(0.48, 0.92)
    p[28] = lm(0.56, 0.92)
    return p


class TestPresence(unittest.TestCase):
    def test_hysteresis(self):
        tr = PresenceTracker(present_seconds=1.5, away_seconds=12)
        self.assertFalse(tr.observe(True, 0.0))
        self.assertTrue(tr.observe(True, 2.0))
        self.assertTrue(tr.observe(False, 10.0))
        self.assertFalse(tr.observe(False, 20.0))

    def test_choose_face_filters_background(self):
        ok, score = choose_face([(200, 80, 160, 160, 0.9), (10, 40, 30, 30, 0.8)],
                                480, 270, 0.06)
        self.assertTrue(ok)
        self.assertAlmostEqual(score, 0.9)
        ok2, _ = choose_face([(0, 0, 20, 20, 0.9)], 480, 270, 0.06)
        self.assertFalse(ok2)


class TestPosture(unittest.TestCase):
    def test_standing_by_knee_angle(self):
        vote = classify_pose(standing_pose())
        self.assertEqual(vote.posture, "standing", vote.reason)

    def test_sitting_by_knee_angle(self):
        vote = classify_pose(sitting_pose())
        self.assertEqual(vote.posture, "sitting", vote.reason)

    def test_hips_above_knees(self):
        p = [lm(0.5, 0.5) for _ in range(33)]
        p[11] = p[12] = lm(0.5, 0.25)
        p[23] = p[24] = lm(0.5, 0.45)
        p[25] = p[26] = lm(0.5, 0.70)
        # 脚踝不可见 → 走“髋高于膝”规则
        p[27] = lm(0.5, 0.95, vis=0.1)
        p[28] = lm(0.5, 0.95, vis=0.1)
        vote = classify_pose(p)
        self.assertEqual(vote.posture, "standing", vote.reason)

    def test_analyzer_face_fallback(self):
        a = PostureAnalyzer(standing_hold=1.0, sitting_hold=1.0, min_samples=5)
        t = 0.0
        for _ in range(10):
            t += 1.0
            a.update(t, pose=None, profile=PostureProfile(face_y=0.55, visible=True),
                     face_present=True, person_present=True)
        self.assertEqual(a.posture, "sitting")
        for _ in range(6):
            t += 1.0
            a.update(t, pose=None, profile=PostureProfile(face_y=0.45, visible=True),
                     face_present=True, person_present=True)
        self.assertEqual(a.posture, "standing")
        self.assertGreaterEqual(a.standing_seconds(t), 1.0)

    def test_analyzer_hysteresis(self):
        a = PostureAnalyzer(standing_hold=2.0, sitting_hold=2.0, min_samples=5)
        t = 0.0
        for _ in range(10):
            t += 1.0
            a.update(t, pose=None, profile=PostureProfile(face_y=0.55, visible=True),
                     face_present=True, person_present=True)
        t += 0.5
        a.update(t, pose=None, profile=PostureProfile(face_y=0.45, visible=True),
                 face_present=True, person_present=True)
        self.assertEqual(a.posture, "sitting")

    def test_manual_override(self):
        a = PostureAnalyzer()
        a.set_manual("standing", 0.0)
        a.update(1.0, pose=None, profile=PostureProfile(face_y=0.55, visible=True),
                 face_present=True, person_present=True)
        self.assertEqual(a.posture, "standing")

    def test_calibration_nearest_profile(self):
        a = PostureAnalyzer(standing_hold=1.0, sitting_hold=1.0)
        a.set_calibration(
            PostureProfile(face_y=0.75, face_h=0.2, shoulder_y=0.9, visible=True),
            PostureProfile(face_y=0.35, face_h=0.2, shoulder_y=0.6, visible=True))
        t = 0.0
        stand = PostureProfile(face_y=0.37, face_h=0.2, shoulder_y=0.62, visible=True)
        for _ in range(3):
            t += 1.0
            a.update(t, pose=None, profile=stand, face_present=True, person_present=True)
        self.assertEqual(a.posture, "standing", a.reason)
        sit_p = PostureProfile(face_y=0.74, face_h=0.2, shoulder_y=0.88, visible=True)
        for _ in range(6):
            t += 1.0
            a.update(t, pose=None, profile=sit_p, face_present=True, person_present=True)
        self.assertEqual(a.posture, "sitting", a.reason)

    def test_calibration_out_of_frame_standing(self):
        a = PostureAnalyzer(standing_hold=1.0, sitting_hold=1.0)
        a.set_calibration(PostureProfile(face_y=0.75, visible=True),
                          PostureProfile(visible=False))
        t = 0.0
        for _ in range(4):
            t += 1.0
            a.update(t, pose=None, profile=PostureProfile(visible=False),
                     face_present=False, person_present=False)
        self.assertEqual(a.posture, "standing")

    def test_face_lost_after_rise_grace(self):
        a = PostureAnalyzer(standing_hold=1.0, sitting_hold=1.0, min_samples=3)
        t = 0.0
        for _ in range(5):
            t += 1.0
            a.update(t, pose=None, profile=PostureProfile(face_y=0.7, visible=True),
                     face_present=True, person_present=True)
        # 脸快速上移后消失
        t += 0.5
        a.update(t, pose=None, profile=PostureProfile(face_y=0.64, visible=True),
                 face_present=True, person_present=True)
        t += 0.2
        for _ in range(4):
            t += 1.0
            a.update(t, pose=None, profile=PostureProfile(visible=False),
                     face_present=False, person_present=True)
        self.assertEqual(a.posture, "standing", a.reason)

    def test_far_sitting_not_standing(self):
        a = PostureAnalyzer(standing_hold=1.0, sitting_hold=1.0, min_samples=3)
        t = 0.0
        for _ in range(6):
            t += 1.0
            a.update(t, pose=None,
                     profile=PostureProfile(face_y=0.70, face_h=0.40, visible=True),
                     face_present=True, person_present=True)
        self.assertEqual(a.posture, "sitting")
        # 坐远：脸变小、视觉位置上移一点，不能判成站立
        for _ in range(4):
            t += 1.0
            a.update(t, pose=None,
                     profile=PostureProfile(face_y=0.62, face_h=0.28, visible=True),
                     face_present=True, person_present=True)
        self.assertEqual(a.posture, "sitting", a.reason)

    def test_body_visible_without_face_not_standing(self):
        a = PostureAnalyzer(standing_hold=1.0, sitting_hold=1.0)
        t = 0.0
        for _ in range(5):
            t += 1.0
            a.update(t, pose=None, profile=PostureProfile(visible=False),
                     face_present=False, person_present=True)
        self.assertNotEqual(a.posture, "standing", a.reason)

    def test_standing_reset_default_is_three_minutes(self):
        self.assertEqual(Config().normalized().standing_reset_seconds, 180.0)


class TestEngine(unittest.TestCase):
    def test_timer_accumulates_when_sitting(self):
        eng, clock, _ = make_engine()
        sit(eng, clock, 10)
        self.assertTrue(eng.present)
        self.assertGreaterEqual(eng.sitting_seconds, 8)

    def test_standing_pauses_sitting_timer(self):
        eng, clock, _ = make_engine()
        sit(eng, clock, 20)
        before = eng.sitting_seconds
        sit(eng, clock, 15, posture="standing")
        self.assertAlmostEqual(eng.sitting_seconds, before, delta=2)
        self.assertEqual(eng.posture, "standing")

    def test_reminder_at_limit(self):
        eng, clock, events = make_engine(sit_minutes=45)
        sit(eng, clock, 45 * 60 + 5)
        self.assertEqual(eng.phase, Phase.BREAK)
        self.assertTrue(any(k == "break_start" for k, _ in events))

    def test_standing_completes_break(self):
        eng, clock, events = make_engine(sit_minutes=1, standing_break_seconds=10)
        sit(eng, clock, 65)
        self.assertEqual(eng.phase, Phase.BREAK)
        # 站起来 12 秒（仍能看到脸）
        sit(eng, clock, 12, posture="standing")
        self.assertEqual(eng.phase, Phase.WATCHING)
        self.assertEqual(eng.stats.breaks, 1)
        self.assertTrue(any(d.startswith("standing") for k, d in events if k == "break_end"))

    def test_manual_break_close_is_immediate(self):
        eng, clock, _ = make_engine(sit_minutes=1)
        sit(eng, clock, 65)
        self.assertEqual(eng.phase, Phase.BREAK)
        eng.confirm_break(clock())
        self.assertEqual(eng.phase, Phase.WATCHING)
        self.assertEqual(eng.stats.breaks, 1)
        self.assertLess(eng.sitting_seconds, 1)

    def test_leaving_completes_break(self):
        eng, clock, _ = make_engine(sit_minutes=1, break_absent_seconds=20)
        sit(eng, clock, 65)
        leave(eng, clock, 22)
        self.assertEqual(eng.phase, Phase.WATCHING)
        self.assertEqual(eng.stats.breaks, 1)

    def test_break_ends_when_out_of_frame(self):
        eng, clock, _ = make_engine(sit_minutes=1, break_absent_seconds=12)
        sit(eng, clock, 65)
        self.assertEqual(eng.phase, Phase.BREAK)
        leave(eng, clock, 13)
        self.assertEqual(eng.phase, Phase.WATCHING)
        self.assertEqual(eng.stats.breaks, 1)

    def test_break_countdown_completes(self):
        eng, clock, _ = make_engine(sit_minutes=1, break_minutes=1)
        sit(eng, clock, 65)
        sit(eng, clock, 65, step=5)  # 一直坐着
        self.assertEqual(eng.phase, Phase.WATCHING)
        self.assertEqual(eng.stats.breaks, 1)

    def test_standing_long_resets_sitting(self):
        eng, clock, events = make_engine(sit_minutes=45, standing_reset_seconds=30)
        sit(eng, clock, 120)
        before = eng.sitting_seconds
        self.assertGreater(before, 100)
        sit(eng, clock, 32, posture="standing")
        self.assertLess(eng.sitting_seconds, 5)
        self.assertTrue(any(k == "reset_by_standing" for k, _ in events))

    def test_away_long_resets_sitting(self):
        eng, clock, _ = make_engine(away_minutes=5)
        sit(eng, clock, 60)
        leave(eng, clock, 5 * 60 + 15)
        self.assertLess(eng.sitting_seconds, 5)

    def test_out_of_frame_three_minutes_restarts(self):
        eng, clock, events = make_engine(sit_minutes=45, away_minutes=5)
        sit(eng, clock, 60)
        before = eng.sitting_seconds
        self.assertGreater(before, 50)
        leave(eng, clock, 200)
        self.assertLess(eng.sitting_seconds, 5)
        self.assertTrue(any(k == "reset_by_break" for k, _ in events))

    def test_snooze_delays(self):
        eng, clock, _ = make_engine(sit_minutes=1, snooze_minutes=2)
        sit(eng, clock, 65)
        eng.snooze(now=clock())
        self.assertEqual(eng.phase, Phase.WATCHING)
        sit(eng, clock, 30)
        self.assertNotEqual(eng.phase, Phase.BREAK)
        sit(eng, clock, 100)
        self.assertEqual(eng.phase, Phase.BREAK)

    def test_pause_stops_timer(self):
        eng, clock, _ = make_engine()
        sit(eng, clock, 10)
        eng.pause()
        before = eng.sitting_seconds
        sit(eng, clock, 30)
        self.assertAlmostEqual(eng.sitting_seconds, before, delta=1)
        eng.resume(clock())
        sit(eng, clock, 10)
        self.assertGreater(eng.sitting_seconds, before + 5)


class TestUiScale(unittest.TestCase):
    def test_dp_scales_with_dpi(self):
        from sitguard import ui
        ui.configure_scale(96)
        self.assertEqual(ui.dp(100), 100)
        ui.configure_scale(192)
        self.assertEqual(ui.dp(100), 200)
        self.assertEqual(ui.dp(420), 840)
        ui.configure_scale(144)
        self.assertEqual(ui.dp(100), 150)
        ui.configure_scale(96)


if __name__ == "__main__":
    unittest.main(verbosity=2)
