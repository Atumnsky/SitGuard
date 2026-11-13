"""按天记录坐/站/离开/暂停的时段，供今日统计与历史回看使用。"""

from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path

from .config import data_dir

log = logging.getLogger("sitguard.daylog")

KINDS = ("sitting", "standing", "away", "paused")
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
