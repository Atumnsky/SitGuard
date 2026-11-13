"""提示音：使用 Windows winsound 播放，失败时静默降级。"""

from __future__ import annotations

import logging
import os
import threading

log = logging.getLogger("sitguard.sound")


def _beep_sequence() -> None:
    try:
        import winsound

        # 三声上行提示音，随后一声长音
        for freq, dur in ((660, 140), (880, 140), (1100, 220), (880, 180)):
            winsound.Beep(freq, dur)
        winsound.Beep(1320, 500)
    except Exception as exc:  # noqa: BLE001
        log.debug("提示音播放失败：%s", exc)


def _play_file(path: str) -> bool:
    try:
        import winsound

        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        return True
    except Exception as exc:  # noqa: BLE001
        log.debug("自定义提示音播放失败：%s", exc)
        return False


def reminder_sound(path: str = "") -> None:
    """播放自定义 wav；为空或失败时使用内置提示音。"""
    if path and os.path.isfile(path) and _play_file(path):
        return
    threading.Thread(target=_beep_sequence, daemon=True).start()


def soft_tick() -> None:
    """离家/回来时的轻提示。"""
    try:
        import winsound

        winsound.MessageBeep(-1)
    except Exception:  # noqa: BLE001
        pass
