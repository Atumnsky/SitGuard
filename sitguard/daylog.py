"""按天记录坐/站/离开/暂停的时段，供今日统计与历史回看使用。"""

from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path

from .config import data_dir

log = logging.getLogger("sitguard.daylog")

KINDS = ("sitting", "standing", "away", "paused", "off")
FILE_NAME = "activity.json"


def _day_key(ts: float) -> str:
    return datetime.fromtimestamp(ts).date().isoformat()


def _midnight_after(ts: float) -> float:
    d = datetime.fromtimestamp(ts).date() + timedelta(days=1)
    return datetime.combine(d, dtime.min).timestamp()


class ActivityTracker:
    def __init__(self, path: Path | None = None, clock=time.time):
        self.clock = clock
        self.path = path or (data_dir() / FILE_NAME)
        self.days: dict[str, list[list]] = {}
        self.kind = "away"
        self.segment_start = self.clock()
        self._last_save = 0.0
        self._load()

    # ---------- 持久化 ----------
    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            days = raw.get("days", {}) if isinstance(raw, dict) else {}
            for key, segs in days.items():
                if isinstance(segs, list):
                    clean = []
                    for seg in segs:
                        if (isinstance(seg, list) and len(seg) == 3
                                and seg[2] in KINDS):
                            clean.append([float(seg[0]), float(seg[1]), str(seg[2])])
                    self.days[key] = clean
        except FileNotFoundError:
            pass
        except Exception:  # noqa: BLE001
            log.exception("读取活动记录失败")
        self._record_offline()
        self._repair_long_standing()
        self._repair_long_sitting()

    def _repair_long_standing(self, max_seconds: float = 4 * 3600,
                              keep_seconds: float = 600) -> None:
        """旧版本在电脑睡眠时可能把几个小时记成一段“站立”。
        超过 4 小时的连续站立几乎不可能，拆成短暂站立 + 离开。"""
        changed = False
        for key, segs in list(self.days.items()):
            out = []
            for start, end, kind in segs:
                if kind == "standing" and end - start > max_seconds:
                    split = min(start + keep_seconds, end)
                    out.append([start, split, "standing"])
                    if end > split:
                        out.append([split, end, "away"])
                    changed = True
                    log.warning("修正异常长站立段：%s %.1f 小时",
                                key, (end - start) / 3600.0)
                else:
                    out.append([start, end, kind])
            self.days[key] = out
        if changed:
            self.save()

    def _last_segment_end(self) -> float:
        ends = [e for segs in self.days.values() for _s, e, _k in segs]
        return max(ends) if ends else 0.0

    def _record_offline(self) -> None:
        """启动时把上次结束到现在的空档记为“关机/未运行”。"""
        last = self._last_segment_end()
        now = self.clock()
        if last and now - last > 120.0:
            self._append(last, now, "off")
            self.save()

    def mark_gap(self, start: float, end: float, kind: str = "off") -> None:
        """把一段没有采集的缺口标记为关机/休眠。"""
        if end <= start:
            return
        start = max(start, self.segment_start or start)
        if self.segment_start is not None and start > self.segment_start:
            self._append(self.segment_start, start, self.kind)
        self._append(start, end, kind)
        self.kind = kind
        self.segment_start = end
        self.save()

    def _repair_long_sitting(self, max_seconds: float = 8 * 3600,
                             keep_seconds: float = 3600) -> None:
        """通宵/睡眠时旧版本可能留下超长坐姿段；超过 8 小时拆成
        1 小时坐姿 + 其余关机/未运行。"""
        changed = False
        for key, segs in list(self.days.items()):
            out = []
            for start, end, kind in segs:
                if kind == "sitting" and end - start > max_seconds:
                    split = min(start + keep_seconds, end)
                    out.append([start, split, "sitting"])
                    if end > split:
                        out.append([split, end, "off"])
                    changed = True
                    log.warning("修正异常长坐姿段：%s %.1f 小时", key,
                                (end - start) / 3600.0)
                else:
                    out.append([start, end, kind])
            self.days[key] = out
        if changed:
            self.save()

    def save(self) -> None:
        try:
            self.close_active()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            for key in list(self.days):
                self._merge_day(key)
            days = {k: v for k, v in self.days.items() if v}
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"version": 1, "days": days},
                                      ensure_ascii=False, indent=1),
                           encoding="utf-8")
            tmp.replace(self.path)
            self._last_save = self.clock()
            self.segment_start = self.clock()
        except Exception:  # noqa: BLE001
            log.exception("保存活动记录失败")

    # ---------- 记录 ----------
    def _append(self, start: float, end: float, kind: str) -> None:
        if end <= start:
            return
        while True:
            key = _day_key(start)
            midnight = _midnight_after(start)
            stop = min(end, midnight)
            if stop > start:
                self.days.setdefault(key, []).append([start, stop, kind])
                self._merge_day(key)
            if end <= midnight:
                break
            start = midnight

    def _merge_day(self, key: str) -> None:
        """合并相邻同类时段，避免每 30 秒保存产生大量碎片。"""
        segs = sorted(self.days.get(key, []), key=lambda x: x[0])
        merged: list[list] = []
        for start, end, kind in segs:
            if merged and merged[-1][2] == kind and start <= merged[-1][1] + 1.5:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end, kind])
        if merged:
            self.days[key] = merged
        else:
            self.days.pop(key, None)

    def update(self, kind: str, now: float | None = None) -> None:
        if kind not in KINDS:
            kind = "away"
        now = self.clock() if now is None else now
        if self.segment_start is None:
            self.kind = kind
            self.segment_start = now
            return
        if kind == self.kind:
            return
        self._append(self.segment_start, now, self.kind)
        self.kind = kind
        self.segment_start = now
        if now - self._last_save >= 30:
            self.save()

    def mark_away(self, start: float, end: float) -> None:
        """把一段没有采集的缺口（睡眠/挂起）记为离开，避免最后一个状态
        跨睡眠延续成几个小时的“站立”。"""
        if end <= start:
            return
        start = max(start, self.segment_start or start)
        if self.segment_start is not None and start > self.segment_start:
            self._append(self.segment_start, start, self.kind)
        self._append(start, end, "away")
        self.kind = "away"
        self.segment_start = end
        self.save()

    def close_active(self, now: float | None = None) -> None:
        now = self.clock() if now is None else now
        if self.segment_start is not None:
            self._append(self.segment_start, now, self.kind)
        self.segment_start = now

    # ---------- 查询 ----------
    def segments_for(self, key: str, now: float | None = None) -> list[list]:
        segs = [list(x) for x in self.days.get(key, [])]
        now = self.clock() if now is None else now
        if key == _day_key(now) and self.segment_start is not None:
            segs.append([self.segment_start, now, self.kind])
        segs.sort(key=lambda x: x[0])
        return segs

    def seconds_between(self, kind: str, start: float, end: float,
                        now: float | None = None) -> float:
        """统计 [start, end) 内某状态的时长，支持跨午夜。"""
        total = 0.0
        for key in {_day_key(start), _day_key(end)}:
            for s, e, k in self.segments_for(key, now):
                if k != kind:
                    continue
                total += max(0.0, min(e, end) - max(s, start))
        return total

    def totals_for(self, key: str, now: float | None = None) -> dict[str, float]:
        totals = {k: 0.0 for k in KINDS}
        for start, end, kind in self.segments_for(key, now):
            totals[kind] = totals.get(kind, 0.0) + max(0.0, end - start)
        return totals

    def first_sit(self, key: str) -> float | None:
        starts = [s for s, _e, k in self.days.get(key, []) if k == "sitting"]
        if key == date.today().isoformat() and self.kind == "sitting":
            starts.append(self.segment_start)
        return min(starts) if starts else None

    def all_days(self, now: float | None = None) -> list[str]:
        now = self.clock() if now is None else now
        keys = {k for k, v in self.days.items() if v}
        keys.add(_day_key(now))
        return sorted(keys, reverse=True)

    def recent(self, count: int = 7, now: float | None = None) -> list[str]:
        now = self.clock() if now is None else now
        today = datetime.fromtimestamp(now).date()
        out = []
        for i in range(count):
            out.append((today - timedelta(days=i)).isoformat())
        return out


def fmt_span(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m = rem // 60
    if h:
        return f"{h}h{m:02d}m"
    return f"{m}m"
