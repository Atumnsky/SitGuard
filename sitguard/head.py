"""头部朝向判断：区分低头（还在）与左右转头/离开。

脸检测在高低头时会丢脸，但姿态关键点通常还能给出鼻子和肩膀。
规则：
- 鼻子明显低于坐姿基线，或最后一段脸部轨迹向下 → 低头（仍算在座）；
- 鼻子横向偏离肩膀中线很多，或最后轨迹向左右/出画 → 离开；
- 没有可靠证据时不强行判断，交给身体在场/离开逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass

from .posture import Landmark, PostureProfile

NOSE = 0
L_SHOULDER, R_SHOULDER = 11, 12


@dataclass
class HeadState:
    down: bool = False
    side: bool = False
    last_x: float | None = None
    last_y: float | None = None
    last_at: float = 0.0
    prev_x: float | None = None
    prev_y: float | None = None
    prev_at: float = 0.0
    baseline_y: float | None = None

    def reset(self) -> None:
        self.down = False
        self.side = False
        self.last_x = self.last_y = None
        self.prev_x = self.prev_y = None
        self.last_at = self.prev_at = 0.0

    def update(self, face_present: bool, profile: PostureProfile,
               pose: list[Landmark] | None, now: float,
               sitting_face_y: float | None = None,
               body_present: bool = False) -> str | None:
        if self.baseline_y is None and sitting_face_y is not None:
            self.baseline_y = sitting_face_y
        if face_present and profile.face_y is not None:
            y = profile.face_y
            if self.baseline_y is None:
                self.baseline_y = y
            self.prev_x, self.prev_y, self.prev_at = self.last_x, self.last_y, self.last_at
            nose = self._nose(pose)
            self.last_x = (profile.face_x if profile.face_x is not None
                           else (nose[0] if nose else None))
            self.last_y = y
            self.last_at = now
            self.side = False
            if y > self.baseline_y + 0.06:
                self.down = True
            elif y < self.baseline_y + 0.03:
                self.down = False
            return "down" if self.down else None

        # 脸不可见：优先用姿态鼻子
        nose = self._nose(pose)
        shoulders = self._shoulders(pose)
        if nose is not None and shoulders is not None:
            nx, ny = nose
            sx, sy, sw = shoulders
            if self.baseline_y is not None and ny > self.baseline_y + 0.02:
                self.down, self.side = True, False
                return "down"
            normal = (self.baseline_y is not None
                      and ny <= self.baseline_y + 0.005)
            if normal:
                self.down, self.side = False, False
            if sw > 1e-6 and abs(nx - sx) / sw > 0.62:
                self.down, self.side = False, True
                return "side"
            if self.baseline_y is not None and ny < self.baseline_y - 0.05:
                self.down, self.side = False, True
                return "side"

        # 姿态看不清时，用最后一段脸部轨迹
        if (self.last_at and now - self.last_at <= 2.0
                and self.last_x is not None and self.last_y is not None
                and self.prev_x is not None and self.prev_y is not None):
            dx = self.last_x - self.prev_x
            dy = self.last_y - self.prev_y
            if dy > 0.03 and dy >= abs(dx):
                self.down, self.side = True, False
            elif abs(dx) > 0.04 and abs(dx) > dy:
                self.down, self.side = False, True
            elif self.baseline_y is not None and self.last_y > self.baseline_y + 0.06:
                self.down, self.side = True, False
            elif self.last_x < 0.12 or self.last_x > 0.88:
                self.down, self.side = False, True
        # 脸和鼻子都看不到，但肩膀仍在坐姿高度：大概率是在低头看书/手机。
        if body_present and not self.side:
            self.down = True
            return "down"
        if self.down:
            return "down"
        if self.side:
            return "side"
        return None

    @staticmethod
    def _nose(pose: list[Landmark] | None) -> tuple[float, float] | None:
        if not pose or len(pose) <= NOSE:
            return None
        lm = pose[NOSE]
        if lm.visibility < 0.3 or not (0.0 <= lm.x <= 1.0 and 0.0 <= lm.y <= 1.0):
            return None
        return (lm.x, lm.y)

    @staticmethod
    def _shoulders(pose: list[Landmark] | None) -> tuple[float, float, float] | None:
        if not pose or len(pose) <= R_SHOULDER:
            return None
        l, r = pose[L_SHOULDER], pose[R_SHOULDER]
        if l.visibility < 0.4 or r.visibility < 0.4:
            return None
        return ((l.x + r.x) / 2, (l.y + r.y) / 2, abs(r.x - l.x))
