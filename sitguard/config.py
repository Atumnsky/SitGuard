"""配置与本地数据存储。"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

log = logging.getLogger("sitguard.config")

APP_DIR_NAME = "SitGuard"


def data_dir() -> Path:
    """数据目录：优先便携目录 data/，不可写时用 %APPDATA%\\SitGuard。"""
    candidates = [Path(__file__).resolve().parent.parent / "data"]
    base = os.environ.get("APPDATA")
    if base:
        candidates.append(Path(base) / APP_DIR_NAME)
    candidates.append(Path.cwd() / "data")
    for path in candidates:
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return path
        except OSError:
            continue
    return Path.cwd()


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass
class Config:
    # 摄像头
    camera_index: int = 0
    camera_enabled: bool = True
    camera_restart_minutes: int = 0   # 0=关闭；定时重启摄像头
    demo_mode: bool = False          # 无摄像头演示：用模拟信号驱动
    language: str = "zh"
    window_width: int = 420
    window_height: int = 524

    # 计时（分钟 / 秒）
    sit_minutes: int = 45            # 连续久坐多少分钟后提醒
    break_minutes: int = 5           # 建议活动时长（休息倒计时）
    away_minutes: int = 5            # 离开多久视为已休息、清零久坐时间

    # 在场检测
    sensitivity: float = 0.6         # 人脸置信度阈值（越低越灵敏）
    present_seconds: float = 1.5     # 连续检测到多久判定“在座”
    away_seconds: float = 12.0       # 连续多久没检测到判定“离开”
    min_face_ratio: float = 0.06     # 人脸宽度至少占画面宽度的比例
    break_absent_seconds: float = 12.0  # 休息期间离开画面多久算完成
    calibration: dict = field(default_factory=dict)  # 坐/站姿态校准档案

    # 姿态（坐/站）
    posture_enabled: bool = True
    pose_model: str = "pose_landmarker_lite.task"
    standing_break_seconds: float = 10.0   # 站立多久自动完成休息
    standing_reset_seconds: float = 180.0  # 站立多久算一次活动、久坐重新计时

    # 提醒
    sound: bool = True
    sound_file: str = ""          # 自定义提示音（wav），空=内置提示音
    overlay_enabled: bool = True    # 是否显示全屏提醒；关闭则只响铃
    sound_repeat: int = 3            # 提醒音重复次数
    snooze_minutes: int = 5          # 临时推迟
    auto_snooze_minutes: int = 2     # 休息中一直没离开时，保持提醒的间隔

    # 行为
    minimize_to_tray: bool = True
    autostart: bool = False
    start_minimized: bool = False
    always_on_top: bool = False
    show_preview: bool = True
    check_updates: bool = False      # 预留
    config_version: int = 2

    def normalized(self) -> "Config":
        c = Config(**asdict(self))
        c.language = "en" if str(c.language).lower().startswith("en") else "zh"
        c.window_width = int(clamp(c.window_width, 150, 2000))
        c.window_height = int(clamp(c.window_height, 150, 2000))
        c.camera_index = int(clamp(c.camera_index, 0, 10))
        c.camera_restart_minutes = int(clamp(c.camera_restart_minutes, 0, 180))
        c.sit_minutes = int(clamp(c.sit_minutes, 1, 480))
        c.break_minutes = int(clamp(c.break_minutes, 1, 60))
        c.away_minutes = int(clamp(c.away_minutes, 1, 120))
        c.sensitivity = float(clamp(c.sensitivity, 0.3, 0.95))
        c.present_seconds = float(clamp(c.present_seconds, 0.0, 30.0))
        c.away_seconds = float(clamp(c.away_seconds, 2.0, 600.0))
        c.min_face_ratio = float(clamp(c.min_face_ratio, 0.02, 0.5))
        c.break_absent_seconds = float(clamp(c.break_absent_seconds, 5.0, 180.0))
        if not isinstance(c.calibration, dict):
            c.calibration = {}
        c.standing_break_seconds = float(clamp(c.standing_break_seconds, 3.0, 120.0))
        c.standing_reset_seconds = float(clamp(c.standing_reset_seconds, 30.0, 900.0))
        c.sound_repeat = int(clamp(c.sound_repeat, 0, 10))
        c.sound_file = str(c.sound_file or "")
        c.overlay_enabled = bool(c.overlay_enabled)
        c.snooze_minutes = int(clamp(c.snooze_minutes, 1, 120))
        c.auto_snooze_minutes = int(clamp(c.auto_snooze_minutes, 1, 30))
        return c

    def copy(self) -> "Config":
        return Config(**asdict(self))


def config_path() -> Path:
    return data_dir() / "config.json"


def load_config(path: Path | None = None) -> Config:
    path = path or config_path()
    cfg = Config()
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(raw, dict):
            known = {f.name for f in fields(Config)}
            for key, value in raw.items():
                if key in known:
                    setattr(cfg, key, value)
            # 旧版默认值迁移：站立 90 秒 → 3 分钟
            if int(raw.get("config_version", 1) or 1) < 2:
                cfg.standing_reset_seconds = 180.0
                cfg.config_version = 2
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as exc:
        log.warning("读取配置失败，使用默认值：%s", exc)
    return cfg.normalized()


def save_config(cfg: Config, path: Path | None = None) -> None:
    path = path or config_path()
    try:
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(asdict(cfg), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(tmp, path)
    except OSError as exc:
        log.warning("保存配置失败：%s", exc)


def stats_path() -> Path:
    return data_dir() / "stats.json"
