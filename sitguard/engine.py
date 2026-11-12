"""计时状态机：久坐累计、久坐提醒、休息完成判定。

核心规则
- 只有“在座且不是站立”时才累计久坐时间；站立期间不计时。
- 久坐达到 sit_minutes 后进入休息阶段（BREAK）。
- 休息阶段满足任意一条即完成：
    * 检测到站立持续 standing_break_seconds（默认 10 秒）；
    * 离开画面持续 confirm_away_seconds（默认 60 秒）；
    * 休息倒计时结束；
    * 用户手动确认（弹窗上的“我站起来了 / 关闭提醒”）。
- 站立持续 standing_reset_seconds（默认 90 秒）也可视为一次活动，久坐清零。

所有时间都用 time.monotonic()，可注入假时钟做单元测试。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from .posture import Posture
from .presence import PresenceTracker


class Phase(str, Enum):
    WATCHING = "watching"
    BREAK = "break"
    PAUSED = "paused"


class BreakReason(str, Enum):
    DUE = "due"
    SNOOZE_DUE = "snooze"
    MANUAL = "manual"


@dataclass
class EngineEvent:
    kind: str
    phase: Phase
    detail: str = ""
    break_reason: BreakReason | None = None


@dataclass
class Stats:
    date: str = ""
    sitting_seconds: float = 0.0
    breaks: int = 0
    reminders: int = 0


@dataclass
class Snapshot:
    phase: Phase = Phase.WATCHING
    present: bool = False
    posture: Posture = "unknown"
    sitting_seconds: float = 0.0
    sit_limit: float = 2700.0
    break_remaining: float = 0.0
    break_total: float = 300.0
    break_reason: BreakReason | None = None
    away_seconds: float = 0.0
    gone_seconds: float = 0.0
    standing_seconds: float = 0.0
    stand_target: float = 10.0
    stand_progress: float = 0.0
    stats: Stats = field(default_factory=Stats)
    camera_state: str = "init"
    camera_message: str = ""
    pose_ok: bool = True
    follow_reminders: int = 0


def _fmt_hms(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


class SessionEngine:
    """核心计时逻辑。UI 每 ~250ms 调用 tick()。"""

    def __init__(self, config, clock: Callable[[], float] = time.monotonic):
        self.config = config
        self.clock = clock
        self.tracker = PresenceTracker(
            present_seconds=config.present_seconds,
            away_seconds=config.away_seconds,
        )
        self.phase = Phase.WATCHING
        self.present = False
        self.present_since: float | None = None
        self.last_present_time: float = 0.0
        self.away_since: float = clock()
        self.sitting_seconds = 0.0
        self.last_tick = clock()
        self.snooze_until = 0.0
        self.break_started: float | None = None
        self.break_reason: BreakReason | None = None
        self.follow_reminders = 0
        self.last_follow_reminder = 0.0
        self._last_seen_ts: float | None = None
        self._listeners: list[Callable[[EngineEvent], None]] = []
        self._last_second_emit = 0.0
        self.stats = Stats(date=self._today())
        self.dirty = False

        # 姿态
        self.posture: Posture = "unknown"
        self.posture_since: float | None = None
        self.posture_reason = ""

    # ---------------------------------------------------------------- 事件
    def add_listener(self, fn: Callable[[EngineEvent], None]) -> None:
        self._listeners.append(fn)

    def _emit(self, kind: str, detail: str = "", reason: BreakReason | None = None) -> None:
        ev = EngineEvent(kind=kind, phase=self.phase, detail=detail, break_reason=reason)
        for fn in list(self._listeners):
            try:
                fn(ev)
            except Exception:  # noqa: BLE001
                import traceback

                traceback.print_exc()

    # ---------------------------------------------------------------- 属性
    @property
    def sit_limit_seconds(self) -> float:
        return float(self.config.sit_minutes) * 60.0

    @property
    def break_total_seconds(self) -> float:
        return float(self.config.break_minutes) * 60.0

    @property
    def standing_target(self) -> float:
        return float(getattr(self.config, "standing_break_seconds", 10.0))

    @property
    def standing_reset_target(self) -> float:
        return float(getattr(self.config, "standing_reset_seconds", 90.0))

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.sit_limit_seconds - self.sitting_seconds)

    @property
    def break_remaining(self) -> float:
        if self.phase is not Phase.BREAK or self.break_started is None:
            return 0.0
        elapsed = self.clock() - self.break_started
        return max(0.0, self.break_total_seconds - elapsed)

    def standing_seconds(self, now: float | None = None) -> float:
        now = self.clock() if now is None else now
        if self.posture != "standing" or self.posture_since is None:
            return 0.0
        return max(0.0, now - self.posture_since)

    # ---------------------------------------------------------------- 输入
    def notify_presence(self, seen: bool, now: float | None = None) -> bool:
        """摄像头检测线程调用：画面里是否有人（脸或身体）。"""
        now = self.clock() if now is None else now
        if seen:
            self._last_seen_ts = now
        was = self.present
        self.present = self.tracker.observe(seen, now)
        if self.present:
            last = self.last_present_time
            self.last_present_time = now
            if self.phase is Phase.WATCHING and self.present_since is None:
                self.present_since = last or now
        if was != self.present:
            if self.present:
                self.away_since = 0.0
                self._emit("present", _fmt_hms(self.sitting_seconds))
            else:
                self.away_since = now
                self._emit("away", _fmt_hms(self.sitting_seconds))
        return self.present

    def notify_posture(self, posture: Posture, now: float | None = None) -> None:
        """姿态线程调用：坐/站/未知。unknown 视为坐着（兼容没有姿态模型的情况）。"""
        now = self.clock() if now is None else now
        if posture == self.posture:
            return
        self.posture = posture
        self.posture_since = now if posture in ("standing", "sitting") else None
        self._emit("posture", posture)

    def set_posture_manual(self, posture: Posture | None, now: float | None = None) -> None:
        """用户手动指定姿态（None 恢复自动）。"""
        now = self.clock() if now is None else now
        self.posture = posture or "unknown"
        self.posture_since = now if posture in ("standing", "sitting") else None
        self._emit("posture_manual", self.posture)

    def _gone_seconds(self, now: float) -> float:
        """距离最后一次看到人（脸或身体）过去了多久。"""
        if self._last_seen_ts is None:
            return 0.0
        return max(0.0, now - self._last_seen_ts)

    def _away_duration(self, now: float) -> float:
        if self.present:
            return 0.0
        if self._last_seen_ts is not None:
            return max(0.0, now - self._last_seen_ts)
        if self.away_since:
            return max(0.0, now - self.away_since)
        return 0.0

    # ---------------------------------------------------------------- 主循环
    def tick(self, now: float | None = None) -> None:
        now = self.clock() if now is None else now
        dt = max(0.0, now - self.last_tick)
        self.last_tick = now
        if dt > 10.0:  # 休眠/卡顿后不要一次性补太多
            dt = min(dt, 2.0)

        self._check_day_rollover()
        if self.phase is Phase.PAUSED:
            self._maybe_second_event(now)
            return

        if self.phase is Phase.WATCHING:
            self._tick_watching(now, dt)
        elif self.phase is Phase.BREAK:
            self._tick_break(now)

        self._maybe_second_event(now)

    def _tick_watching(self, now: float, dt: float) -> None:
        standing = self.posture == "standing"
        if self.present and not standing:
            self.sitting_seconds += dt
            self.stats.sitting_seconds += dt
            self.dirty = True

        # 离开/站立足够久 → 重新计时（取 3 分钟与“离开算休息”中较短者）
        reset_after = min(float(self.config.away_minutes) * 60.0,
                          self.standing_reset_target)
        if (not self.present and self.away_since
                and now - self.away_since >= reset_after):
            if self.sitting_seconds > 0:
                self.sitting_seconds = 0.0
                self._emit("reset_by_break", "")
        # 站立足够久 → 视为活动，清零
        if (standing and self.standing_seconds(now) >= self.standing_reset_target
                and self.sitting_seconds > 0):
            self.sitting_seconds = 0.0
            self._emit("reset_by_standing", f"{int(self.standing_seconds(now))} 秒")

        if (self.present and not standing and self.snooze_until <= now
                and self.sitting_seconds >= self.sit_limit_seconds):
            self._start_break(BreakReason.DUE)

    def _tick_break(self, now: float) -> None:
        if self.break_started is None:
            return
        elapsed = now - self.break_started
        away_time = self._away_duration(now)

        # 1) 站立达标 → 完成（可以站在电脑前）
        if self.posture == "standing":
            stood = self.standing_seconds(now)
            if stood >= self.standing_target:
                self._finish_break(now, why="standing", n=int(stood))
                return
        # 2) 离开画面足够久（站起来后整个人离开镜头也算）→ 完成
        gone = self._gone_seconds(now)
        if gone >= float(getattr(self.config, "break_absent_seconds", 12.0)):
            self._finish_break(now, why="gone", n=int(gone))
            return
        # 3) 倒计时结束
        if elapsed >= self.break_total_seconds:
            self._finish_break(now, why="timeout")
            return
        # 4) 一直坐着 → 定时再催
        interval = max(30.0, float(self.config.auto_snooze_minutes) * 60.0)
        if (self.present and self.posture != "standing"
                and now - self.last_follow_reminder >= interval):
            self.last_follow_reminder = now
            self.follow_reminders += 1
            self._emit("break_follow", "还在座位上")

    def _maybe_second_event(self, now: float) -> None:
        if now - self._last_second_emit >= 1.0:
            self._last_second_emit = now
            self._emit("tick")

    # ---------------------------------------------------------------- 动作
    def start(self, now: float | None = None) -> None:
        now = self.clock() if now is None else now
        self.last_tick = now
        self.away_since = now
        self._emit("started")

    def pause(self, now: float | None = None) -> None:
        if self.phase is Phase.BREAK:
            return
        self.phase = Phase.PAUSED
        self._emit("paused")

    def resume(self, now: float | None = None) -> None:
        if self.phase is not Phase.PAUSED:
            return
        now = self.clock() if now is None else now
        self.phase = Phase.WATCHING
        self.last_tick = now
        if self.away_since:
            self.away_since = now
        self._emit("resumed")

    def snooze(self, minutes: float | None = None, now: float | None = None) -> None:
        now = self.clock() if now is None else now
        minutes = self.config.snooze_minutes if minutes is None else minutes
        if self.phase is Phase.BREAK:
            self.phase = Phase.WATCHING
            self.break_started = None
            self.break_reason = None
            self.last_follow_reminder = 0.0
            self.snooze_until = now + minutes * 60.0
            self.sitting_seconds = min(self.sitting_seconds, self.sit_limit_seconds * 0.999)
            self._emit("snoozed", f"{int(minutes)} 分钟")
        elif self.phase is Phase.WATCHING:
            self.snooze_until = now + minutes * 60.0
            self._emit("snoozed", f"{int(minutes)} 分钟")

    def confirm_break(self, now: float | None = None) -> None:
        """用户明确表示已站起来 / 主动关闭提醒 → 立即完成休息。"""
        now = self.clock() if now is None else now
        if self.phase is not Phase.BREAK:
            return
        self._finish_break(now, why="manual")

    def force_break(self, now: float | None = None) -> None:
        now = self.clock() if now is None else now
        if self.phase is Phase.BREAK:
            return
        self.phase = Phase.WATCHING
        self._start_break(BreakReason.MANUAL, now)

    def _start_break(self, reason: BreakReason, now: float | None = None) -> None:
        now = self.clock() if now is None else now
        self.phase = Phase.BREAK
        self.break_started = now
        self.break_reason = reason
        self.snooze_until = 0.0
        self.follow_reminders = 0
        self.last_follow_reminder = now
        self.stats.reminders += 1
        self.sitting_seconds = min(self.sitting_seconds, self.sit_limit_seconds)
        self._emit("break_start", _fmt_hms(self.sitting_seconds), reason)

    def _finish_break(self, now: float | None = None, why: str = "timeout",
                      n: int = 0) -> None:
        now = self.clock() if now is None else now
        self.phase = Phase.WATCHING
        self.sitting_seconds = 0.0
        self.stats.breaks += 1
        self.break_started = None
        self.break_reason = None
        self.last_tick = now
        self.snooze_until = 0.0
        self._emit("break_end", f"{why}:{n}" if n else why)

    def reset_sitting(self) -> None:
        self.sitting_seconds = 0.0
        self.snooze_until = 0.0
        self._emit("reset")

    # ---------------------------------------------------------------- 统计
    def _today(self) -> str:
        return time.strftime("%Y-%m-%d")

    def _check_day_rollover(self) -> None:
        today = self._today()
        if self.stats.date != today:
            self.stats = Stats(date=today)
            self.dirty = True

    def snapshot(self, camera_state: str = "init", camera_message: str = "",
                 pose_ok: bool = True) -> Snapshot:
        now = self.clock()
        stood = self.standing_seconds(now)
        target = max(1.0, self.standing_target)
        return Snapshot(
            phase=self.phase,
            present=self.present,
            posture=self.posture,
            sitting_seconds=self.sitting_seconds,
            sit_limit=self.sit_limit_seconds,
            break_remaining=self.break_remaining,
            break_total=self.break_total_seconds,
            break_reason=self.break_reason,
            away_seconds=self._away_duration(now),
            gone_seconds=self._gone_seconds(now),
            standing_seconds=stood,
            stand_target=target,
            stand_progress=min(1.0, stood / target),
            stats=self.stats,
            camera_state=camera_state,
            camera_message=camera_message,
            pose_ok=pose_ok,
            follow_reminders=self.follow_reminders,
        )
