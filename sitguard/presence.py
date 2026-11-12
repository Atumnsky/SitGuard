"""在场检测的时序平滑（防抖）。

摄像头逐帧检测到人脸只能说明“这一帧有人”，而人可能只是转头、离开、
或者被身后的人误触发。这里用时间窗口做迟滞（hysteresis）：
连续看到才算在座，连续看不到才算离开。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PresenceTracker:
    present_seconds: float = 1.5   # 连续看到多久 → 在座
    away_seconds: float = 12.0     # 连续看不到多久 → 离开
    present: bool = False
    last_seen: float | None = None      # 最近一次看见人脸的时间
    first_seen: float | None = None     # 本轮连续看见的起点
    last_absent: float | None = None    # 最近一次确认离开的时间

    def observe(self, seen: bool, now: float) -> bool:
        """输入一次观测，返回当前平滑后的在场状态。"""
        if seen:
            if self.first_seen is None:
                self.first_seen = now
            self.last_seen = now
            if not self.present and now - self.first_seen >= self.present_seconds:
                self.present = True
        else:
            if self.present:
                if self.last_seen is not None and now - self.last_seen >= self.away_seconds:
                    self.present = False
                    self.first_seen = None
                    self.last_absent = now
            else:
                self.first_seen = None
        return self.present

    def seconds_since_seen(self, now: float) -> float | None:
        if self.last_seen is None:
            return None
        return max(0.0, now - self.last_seen)

    def reset(self) -> None:
        self.present = False
        self.last_seen = None
        self.first_seen = None
        self.last_absent = None


@dataclass
class FaceCandidate:
    x: float
    y: float
    w: float
    h: float
    score: float

    @property
    def area(self) -> float:
        return self.w * self.h


@dataclass
class FaceCandidate:
    x: float
    y: float
    w: float
    h: float
    score: float

    @property
    def area(self) -> float:
        return self.w * self.h


def choose_face(faces: list[tuple[float, float, float, float, float]],
                frame_w: int, frame_h: int,
                min_face_ratio: float) -> tuple[bool, float]:
    """从 YuNet 结果中挑出“屏幕前的人”。

    faces 每项为 (x, y, w, h, score)。优先选面积最大的脸，
    但要求脸足够大、且水平位置大致在画面中部（排除远处路人）。
    返回 (是否在座, 最佳得分)。
    """
    best = FaceCandidate(0, 0, 0, 0, 0.0)
    found = False
    for x, y, w, h, score in faces:
        score = float(score)
        if w < frame_w * min_face_ratio or h < frame_h * min_face_ratio * 0.8:
            continue
        cx = x + w / 2.0
        cy = y + h / 2.0
        # 太靠画面边缘的一般是背景里的人
        if not (0.12 * frame_w <= cx <= 0.88 * frame_w):
            continue
        if not (0.02 * frame_h <= cy <= 0.98 * frame_h):
            continue
        candidate = FaceCandidate(x, y, w, h, score)
        if not found or candidate.area > best.area:
            best = candidate
            found = True
    return found, best.score if found else 0.0

