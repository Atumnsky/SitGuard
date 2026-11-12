"""提示音：使用 Windows winsound 播放，失败时静默降级。"""

from __future__ import annotations

import logging
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


def reminder_sound() -> None:
    threading.Thread(target=_beep_sequence, daemon=True).start()


def soft_tick() -> None:
    """离家/回来时的轻提示。"""
    try:
        import winsound

        winsound.MessageBeep(-1)
    except Exception:  # noqa: BLE001
        pass
