"""坐/站姿态分析。

两种模式：
1. **校准模式（推荐）**：用户分别记录“坐姿”和“站姿”时的画面特征
   （脸中心高度、脸大小、肩部高度；站姿可能整个人离开画面）。
   判定时比较当前特征与两个档案的距离，最接近且差距足够大才切换。
2. **自动模式（未校准时）**：按可靠性依次使用
   腿部膝角 → 髋/膝高度 → 躯干比例 → 脸部高度变化 → 肩部高度变化 →
   看不到脸但看得到身体 → 起身后离开画面。

所有切换都有数秒迟滞，避免抬头、转头造成误判。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

Posture = Literal["sitting", "standing", "unknown"]

NOSE = 0
L_SHOULDER, R_SHOULDER = 11, 12
L_HIP, R_HIP = 23, 24
L_KNEE, R_KNEE = 25, 26
L_ANKLE, R_ANKLE = 27, 28


@dataclass
class Landmark:
    x: float
    y: float
    visibility: float = 1.0


@dataclass
class PostureProfile:
    """一帧画面的姿态特征（归一化到 0..1）。"""
    face_y: float | None = None      # 脸中心 y
    face_h: float | None = None      # 脸高度 / 画面高度
    shoulder_y: float | None = None  # 肩部 y
    visible: bool = True             # 是否能看到脸

    def to_dict(self) -> dict:
        return {"face_y": self.face_y, "face_h": self.face_h,
                "shoulder_y": self.shoulder_y, "visible": self.visible}

    @classmethod
    def from_dict(cls, raw: dict | None) -> "PostureProfile | None":
        if not isinstance(raw, dict):
            return None
        try:
            return cls(
                face_y=None if raw.get("face_y") is None else float(raw["face_y"]),
                face_h=None if raw.get("face_h") is None else float(raw["face_h"]),
                shoulder_y=(None if raw.get("shoulder_y") is None
                            else float(raw["shoulder_y"])),
                visible=bool(raw.get("visible", True)),
            )
        except (TypeError, ValueError):
            return None


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    if n % 2:
        return ordered[n // 2]
    return (ordered[n // 2 - 1] + ordered[n // 2]) / 2


def median_profile(profiles: list[PostureProfile]) -> PostureProfile:
    """把多帧特征合成一个稳定档案。"""
    visible = [p for p in profiles if p.visible]
    if not visible:
        shoulders = [p.shoulder_y for p in profiles if p.shoulder_y is not None]
        return PostureProfile(visible=False,
                              shoulder_y=_median(shoulders) if shoulders else None)
    face_ys = [p.face_y for p in visible if p.face_y is not None]
    face_hs = [p.face_h for p in visible if p.face_h is not None]
    shoulders = [p.shoulder_y for p in visible if p.shoulder_y is not None]
    return PostureProfile(
        face_y=_median(face_ys) if face_ys else None,
        face_h=_median(face_hs) if face_hs else None,
        shoulder_y=_median(shoulders) if shoulders else None,
        visible=True,
    )


def extract_profile(faces, pose: list[Landmark] | None,
                    frame_w: int, frame_h: int) -> PostureProfile:
    """从一帧的人脸框和姿态关键点提取特征。"""
    profile = PostureProfile(visible=False)
    if faces:
        x, y, w, h, _score = max(faces, key=lambda f: f[2] * f[3])
        if frame_h > 0:
            profile.face_y = (y + h / 2) / frame_h
            profile.face_h = h / frame_h
            profile.visible = True
    if pose and len(pose) > 12:
        ys = [pose[i].y for i in (L_SHOULDER, R_SHOULDER)
              if pose[i].visibility >= 0.4 and 0 <= pose[i].y <= 1.2]
        if ys:
            profile.shoulder_y = min(ys)
    return profile


def _dist(a: PostureProfile, b: PostureProfile) -> float | None:
    """两个可见档案之间的距离（缺项自动忽略）。"""
    total = 0.0
    weight = 0.0
    if a.face_y is not None and b.face_y is not None:
        total += 1.0 * abs(a.face_y - b.face_y)
        weight += 1.0
    if a.face_h is not None and b.face_h is not None:
        total += 0.6 * abs(a.face_h - b.face_h)
        weight += 0.6
    if a.shoulder_y is not None and b.shoulder_y is not None:
        total += 0.8 * abs(a.shoulder_y - b.shoulder_y)
        weight += 0.8
    if weight == 0:
        return None
    return total / weight


@dataclass
class PoseVote:
    posture: Posture = "unknown"
    reason: str = ""
    torso_ratio: float | None = None


def _angle(a: Landmark, b: Landmark, c: Landmark) -> float:
    v1 = (a.x - b.x, a.y - b.y)
    v2 = (c.x - b.x, c.y - b.y)
    n1 = math.hypot(*v1)
    n2 = math.hypot(*v2)
    if n1 < 1e-6 or n2 < 1e-6:
        return 180.0
    cos = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))
    return math.degrees(math.acos(cos))


def _vis(lms: list[Landmark], idx: int, threshold: float = 0.5) -> bool:
    return len(lms) > idx and lms[idx].visibility >= threshold


def classify_pose(lms: list[Landmark] | None) -> PoseVote:
    """只依赖关键点判断姿态。"""
    if not lms or len(lms) < 29:
        return PoseVote("unknown", "无关键点")

    for side, (hip, knee, ankle) in (("左", (L_HIP, L_KNEE, L_ANKLE)),
                                     ("右", (R_HIP, R_KNEE, R_ANKLE))):
        if _vis(lms, hip, 0.5) and _vis(lms, knee, 0.5) and _vis(lms, ankle, 0.4):
            ang = _angle(lms[hip], lms[knee], lms[ankle])
            if ang >= 150:
                return PoseVote("standing", f"{side}腿膝角 {ang:.0f}°")
            if 40 <= ang <= 120:
                return PoseVote("sitting", f"{side}腿膝角 {ang:.0f}°")

    if all(_vis(lms, i) for i in (L_HIP, R_HIP, L_KNEE, R_KNEE)):
        hip_y = min(lms[L_HIP].y, lms[R_HIP].y)
        knee_y = min(lms[L_KNEE].y, lms[R_KNEE].y)
        if hip_y < knee_y - 0.10:
            return PoseVote("standing", "髋部明显高于膝")
        if abs(hip_y - knee_y) <= 0.07:
            return PoseVote("sitting", "髋与膝高度接近")

    if all(_vis(lms, i) for i in (L_SHOULDER, R_SHOULDER, L_HIP, R_HIP)):
        sw = math.dist((lms[L_SHOULDER].x, lms[L_SHOULDER].y),
                       (lms[R_SHOULDER].x, lms[R_SHOULDER].y))
        torso = (math.dist((lms[L_SHOULDER].x, lms[L_SHOULDER].y),
                           (lms[L_HIP].x, lms[L_HIP].y))
                 + math.dist((lms[R_SHOULDER].x, lms[R_SHOULDER].y),
                             (lms[R_HIP].x, lms[R_HIP].y))) / 2
        if sw > 1e-6:
            return PoseVote("unknown", "躯干比例", torso / sw)

    return PoseVote("unknown", "关键点不足")


class PostureAnalyzer:
    """把逐帧特征融合成稳定的坐/站状态。"""

    def __init__(self, *, standing_hold: float = 2.5, sitting_hold: float = 3.0,
                 face_shift_ratio: float = 0.06, shoulder_shift_ratio: float = 0.05,
                 torso_ratio_gain: float = 0.22, min_samples: int = 10,
                 samples_max: int = 150):
        self.standing_hold = standing_hold
        self.sitting_hold = sitting_hold
        self.face_shift_ratio = face_shift_ratio
        self.shoulder_shift_ratio = shoulder_shift_ratio
        self.torso_ratio_gain = torso_ratio_gain
        self.min_samples = min_samples
        self.samples_max = samples_max

        self.posture: Posture = "unknown"
        self.since: float | None = None
        self.reason: str = ""
        self.manual: Posture | None = None

        self.sitting_profile: PostureProfile | None = None
        self.standing_profile: PostureProfile | None = None

        self._candidate: Posture = "unknown"
        self._candidate_since: float | None = None
        self._face_base: float | None = None
        self._face_samples: list[float] = []
        self._face_h_base: float | None = None
        self._face_h_samples: list[float] = []
        self._shoulder_base: float | None = None
        self._shoulder_samples: list[float] = []
        self._torso_base: float | None = None
        self._torso_samples: list[float] = []
        self._last_face_y: float | None = None
        self._last_face_at: float | None = None
        self._lost_after_rise_at: float | None = None
        self._grace_until = 0.0

    # ---------------------------------------------------------------- 外部接口
    def set_calibration(self, sitting: PostureProfile | None,
                        standing: PostureProfile | None) -> None:
        self.sitting_profile = sitting
        self.standing_profile = standing
        self._face_base = sitting.face_y if sitting and sitting.visible else None
        self._shoulder_base = sitting.shoulder_y if sitting else None

    def set_manual(self, value: Posture | None, now: float) -> None:
        self.manual = value
        if value:
            self._candidate = "unknown"
            self._candidate_since = None
            self._apply(value, now, "手动")

    def update(self, now: float, *, pose: list[Landmark] | None,
               profile: PostureProfile,
               face_present: bool, person_present: bool) -> Posture:
        if self.manual:
            return self.posture
        if not person_present and not profile.visible:
            # 完全看不到人：若校准时站姿也不在画面里，按“起身”处理
            if (self.standing_profile is not None
                    and not self.standing_profile.visible):
                self._candidate_apply(now, "standing", "站姿校准为离开画面")
            else:
                self._reset_candidate()
                self._apply("unknown", now, "无人")
            return self.posture

        candidate, reason = self._decide(now, pose, profile, face_present, person_present)

        # 站起来后很快离开画面：给 20 秒“站立”宽限
        if candidate == "unknown" and not face_present:
            if self._lost_after_rise_at and now - self._lost_after_rise_at <= 1.5:
                self._grace_until = max(self._grace_until, now + 20)
            if now <= self._grace_until:
                candidate, reason = "standing", "起身后离开画面"

        if candidate == "unknown":
            return self.posture
        self._candidate_apply(now, candidate, reason)
        return self.posture

    def _decide(self, now: float, pose: list[Landmark] | None,
                profile: PostureProfile, face_present: bool,
                person_present: bool) -> tuple[Posture, str]:
        # 0) 校准档案：最近邻
        if (self.sitting_profile is not None and self.standing_profile is not None
                and self.standing_profile.visible):
            if profile.visible:
                d_sit = _dist(profile, self.sitting_profile)
                d_stand = _dist(profile, self.standing_profile)
                if d_sit is not None and d_stand is not None:
                    margin = 0.035
                    if d_stand + margin < d_sit:
                        return "standing", f"接近站姿档案（{d_stand:.2f}）"
                    if d_sit + margin < d_stand:
                        return "sitting", f"接近坐姿档案（{d_sit:.2f}）"

        # 1) 关键点直接判定
        vote = classify_pose(pose)
        if vote.posture != "unknown":
            return vote.posture, vote.reason
        if vote.torso_ratio:
            self._torso_samples.append(vote.torso_ratio)
            if len(self._torso_samples) > 40:
                self._torso_samples.pop(0)
            if self._torso_base is None and len(self._torso_samples) >= 6:
                self._torso_base = sorted(self._torso_samples)[len(self._torso_samples) // 2]
            if self._torso_base:
                gain = vote.torso_ratio / self._torso_base
                if gain >= 1 + self.torso_ratio_gain:
                    return "standing", f"躯干延长 {gain:.2f}×"
                if gain <= 1 + self.torso_ratio_gain * 0.35:
                    return "sitting", f"躯干比例 {gain:.2f}×"

        # 2) 肩部高度变化（比脸稳定）
        if profile.shoulder_y is not None:
            if self._shoulder_base is None:
                self._shoulder_samples.append(profile.shoulder_y)
                if len(self._shoulder_samples) >= self.min_samples:
                    self._shoulder_base = _median(self._shoulder_samples)
            else:
                rise = self._shoulder_base - profile.shoulder_y
                if rise >= self.shoulder_shift_ratio:
                    return "standing", f"肩部上移 {rise * 100:.0f}%"
                if rise < self.shoulder_shift_ratio * 0.5:
                    return "sitting", "肩部位置稳定"

        # 3) 脸部高度变化
        if face_present and profile.face_y is not None:
            y = profile.face_y
            if self._last_face_y is not None and y < self._last_face_y - 0.04:
                self._lost_after_rise_at = None
            self._last_face_y = y
            self._last_face_at = now
            if profile.face_h is not None:
                self._face_h_samples.append(profile.face_h)
                if len(self._face_h_samples) > self.samples_max:
                    self._face_h_samples.pop(0)
                if (self._face_h_base is None
                        and len(self._face_h_samples) >= self.min_samples):
                    self._face_h_base = _median(self._face_h_samples)
            if self._face_base is None:
                self._face_samples.append(y)
                if len(self._face_samples) >= self.min_samples:
                    self._face_base = _median(self._face_samples)
            else:
                rise = self._face_base - y
                # 坐远时脸会变小、位置变化，不能当成站立
                if (self._face_h_base and profile.face_h
                        and profile.face_h < self._face_h_base * 0.8
                        and rise < self.face_shift_ratio * 2):
                    return "sitting", "距离变远"
                if rise >= self.face_shift_ratio:
                    return "standing", f"脸部上移 {rise * 100:.0f}%"
                if rise <= self.face_shift_ratio * 0.3:
                    return "sitting", "脸部位置稳定"
        elif self._last_face_y is not None:
            # 脸刚刚消失：只有明显上移后才按“起身”宽限
            if self._face_base is not None and self._face_base - self._last_face_y >= 0.03:
                self._lost_after_rise_at = now
            self._last_face_y = None

        # 4) 看得到身体但看不到脸：不能直接判定站立（可能只是坐远了）
        return "unknown", ""

    def _candidate_apply(self, now: float, candidate: Posture, reason: str) -> None:
        if candidate == self.posture:
            self._reset_candidate()
            return
        if candidate != self._candidate:
            self._candidate = candidate
            self._candidate_since = now
        hold = self.standing_hold if candidate == "standing" else self.sitting_hold
        if self._candidate_since is not None and now - self._candidate_since >= hold:
            self._apply(candidate, now, reason)

    def _apply(self, state: Posture, now: float, reason: str) -> None:
        self.posture = state
        self.reason = reason
        self.since = now
        self._reset_candidate()

    def _reset_candidate(self) -> None:
        self._candidate = "unknown"
        self._candidate_since = None

    def standing_seconds(self, now: float) -> float:
        if self.posture != "standing" or self.since is None:
            return 0.0
        return max(0.0, now - self.since)

    def reset(self) -> None:
        self.posture = "unknown"
        self.since = None
        self.reason = ""
        self.manual = None
        self._reset_candidate()
        self._face_base = None
        self._face_samples.clear()
        self._face_h_base = None
        self._face_h_samples.clear()
        self._shoulder_base = None
        self._shoulder_samples.clear()
        self._torso_base = None
        self._torso_samples.clear()
        self._last_face_y = None
        self._last_face_at = None
        self._lost_after_rise_at = None
        self._grace_until = 0.0
