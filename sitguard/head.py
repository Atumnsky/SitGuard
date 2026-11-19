"""头部朝向判断：区分低头（还在）与左右转头/离开。

低头只在脸部框的下边缘接近画面底部时触发，稍微比坐姿低一点不算。
脸消失时用最后的框位置/姿态鼻子辅助，左右转头仍判离开。
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
    last_bottom: float | None = None
    last_at: float = 0.0
    prev_x: float | None = None
    prev_y: float | None = None
    prev_at: float = 0.0
    baseline_bottom: float | None = None

    def reset(self) -> None:
        self.down = False
        self.side = False
        self.last_x = self.last_y = self.last_bottom = None
        self.prev_x = self.prev_y = None
        self.last_at = self.prev_at = 0.0

    def _threshold(self) -> float:
        base = self.baseline_bottom or 0.0
        return max(0.90, base + 0.08)

    def update(self, face_present: bool, profile: PostureProfile,
               pose: list[Landmark] | None, now: float,
               sitting_face_y: float | None = None,
               body_present: bool = False,
               sitting_bottom: float | None = None) -> str | None:
        if self.baseline_bottom is None and sitting_bottom is not None:
            self.baseline_bottom = sitting_bottom
        threshold = self._threshold()

        if face_present and profile.face_y is not None:
            y = profile.face_y
            h = profile.face_h or 0.0
            bottom = y + h / 2.0
            self.prev_x, self.prev_y, self.prev_at = self.last_x, self.last_y, self.last_at
            nose = self._nose(pose)
            self.last_x = (profile.face_x if profile.face_x is not None
                           else (nose[0] if nose else None))
            self.last_y = y
            self.last_bottom = bottom
            self.last_at = now
            self.side = False
            self.down = bottom >= threshold
            return "down" if self.down else None

        # 脸不可见：优先用姿态鼻子
        nose = self._nose(pose)
        shoulders = self._shoulders(pose)
        if nose is not None and shoulders is not None:
            nx, ny = nose
            sx, sy, sw = shoulders
            if ny > sy + 0.08:      # 鼻子在肩膀下方：背景误检
                nose = None
        if nose is not None and shoulders is not None:
            nx, ny = nose
            sx, sy, sw = shoulders
            if ny < 0.85:
                self.down = False
            if ny >= 0.90:
                self.down, self.side = True, False
                return "down"
            if sw > 1e-6 and abs(nx - sx) / sw > 0.62:
                self.down, self.side = False, True
                return "side"

        # 脸消失后：只有最后的框下缘接近底部，或明显向下移动且已接近底部
        if self.last_bottom is not None:
            if self.last_bottom >= threshold - 0.03:
                self.down, self.side = True, False
            elif (self.last_at and now - self.last_at <= 2.0
                  and self.last_y is not None and self.prev_y is not None
                  and self.last_y - self.prev_y > 0.03
                  and self.last_bottom >= 0.88):
                self.down, self.side = True, False
            elif self.down and self.last_bottom < threshold - 0.08:
                self.down = False

        # 左右转头：强横向轨迹 + 出画边缘
        if (self.last_at and now - self.last_at <= 2.0
                and self.last_x is not None and self.prev_x is not None
                and abs(self.last_x - self.prev_x) > 0.12
                and (self.last_x < 0.15 or self.last_x > 0.85)):
            self.down, self.side = False, True

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
        if lm.visibility < 0.5 or not (0.0 <= lm.x <= 1.0 and 0.0 <= lm.y <= 1.0):
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
