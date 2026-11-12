"""摄像头画面健康检测：识别“电视机雪花”式噪声画面。

真实摄像头画面相邻像素高度相关；传感器/驱动失效时常常输出随机噪声：
相邻像素几乎不相关、帧间差异很大、整体偏灰。连续检测到这种画面约 2 秒
就判定为雪花，交由采集线程重启摄像头。
"""

from __future__ import annotations

import numpy as np


class FrameHealth:
    def __init__(self, snow_seconds: float = 2.0, black_seconds: float = 8.0):
        self.snow_seconds = snow_seconds
        self.black_seconds = black_seconds
        self._bad_since: float | None = None
        self._black_since: float | None = None
        self._prev: np.ndarray | None = None
        self.last_stats = {"mean": 0.0, "std": 0.0, "corr": 1.0, "diff": 0.0}

    def update(self, frame, now: float) -> str | None:
        """返回 "snow" / "black" 表示需要重启摄像头，正常返回 None。"""
        if frame is None or frame.size == 0:
            return None
        try:
            gray = frame.astype(np.float32).mean(axis=2)
            h, w = gray.shape
            step_y = max(1, h // 36)
            step_x = max(1, w // 64)
            small = gray[::step_y, ::step_x]
            std = float(small.std())
            mean = float(small.mean())
            a = small[:, :-1].ravel()
            b = small[:, 1:].ravel()
            if a.std() > 1e-3 and b.std() > 1e-3:
                corr = float(np.corrcoef(a, b)[0, 1])
            else:
                corr = 1.0
            diff = 0.0 if self._prev is None else float(np.mean(np.abs(small - self._prev)))
            self._prev = small
            self.last_stats = {"mean": mean, "std": std, "corr": corr, "diff": diff}

            # 雪花：亮度正常、空间细节随机、相邻像素不相关、帧间剧烈变化
            bad = mean > 15.0 and std > 15.0 and corr < 0.25 and diff > 8.0
            if bad:
                self._black_since = None
                if self._bad_since is None:
                    self._bad_since = now
                if now - self._bad_since >= self.snow_seconds:
                    self._bad_since = None
                    self._prev = None
                    return "snow"
            else:
                self._bad_since = None

            # 全黑且几乎无噪声：可能是驱动挂了或摄像头被遮挡
            black = mean < 3.0 and std < 8.0
            if black:
                if self._black_since is None:
                    self._black_since = now
                if now - self._black_since >= self.black_seconds:
                    self._black_since = None
                    self._prev = None
                    return "black"
            else:
                self._black_since = None
            return None
        except Exception:  # noqa: BLE001
            return None
