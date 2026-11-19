"""提示音：内置合成音 + 自定义 WAV，使用 Windows winsound 播放。"""

from __future__ import annotations

import io
import logging
import math
import os
import struct
import threading
import wave

log = logging.getLogger("sitguard.sound")

# 名称 -> [(频率 Hz, 时长 ms, 波形)]，波形缺省 sine，可选 square
BUILTINS: dict[str, list[tuple]] = {
    "classic": [(660, 110), (880, 110), (1100, 180), (880, 140)],
    "bright": [(1046, 80), (1318, 80), (1568, 140)],
    "drop": [(1200, 80), (900, 80), (600, 170)],
    "rise": [(600, 80), (800, 80), (1000, 170)],
    "dingdong": [(1318, 170), (1046, 240)],
    "wood": [(240, 55), (180, 80)],
    "bird": [(1800, 55), (2200, 60), (1980, 90)],
    "retro": [(523, 70, "square"), (659, 70, "square"),
              (784, 70, "square"), (1046, 120, "square")],
    "sit_soft": [(520, 70), (400, 110)],
    "stand_up": [(700, 70), (950, 130)],
    "none": [],
}
SOUND_NAMES = tuple(BUILTINS)
_CACHE: dict[str, bytes] = {}


def _wav_bytes(name: str) -> bytes:
    if name in _CACHE:
        return _CACHE[name]
    seq = BUILTINS.get(name) or BUILTINS["classic"]
    rate = 44100
    frames = bytearray()
    for item in seq:
        freq, dur = item[0], item[1]
        wave_type = item[2] if len(item) > 2 else "sine"
        n = max(1, int(rate * dur / 1000.0))
        fade = max(1, int(rate * 0.008))
        for i in range(n):
            env = min(1.0, i / fade, (n - i) / fade)
            value = math.sin(2 * math.pi * freq * i / rate)
            if wave_type == "square":
                value = 1.0 if value >= 0 else -1.0
            frames += struct.pack("<h", int(12000 * env * value))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    data = buf.getvalue()
    _CACHE[name] = data
    return data


def _play_bytes(data: bytes) -> None:
    try:
        import winsound

        winsound.PlaySound(data, winsound.SND_MEMORY)
    except Exception as exc:  # noqa: BLE001
        log.debug("内置提示音播放失败：%s", exc)


def play_builtin(name: str) -> None:
    if name == "none" or name not in BUILTINS:
        return
    data = _wav_bytes(name)
    threading.Thread(target=_play_bytes, args=(data,), daemon=True).start()


def _play_file(path: str) -> bool:
    try:
        import winsound

        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        return True
    except Exception as exc:  # noqa: BLE001
        log.debug("自定义提示音播放失败：%s", exc)
        return False


def reminder_sound(path: str = "", name: str = "classic") -> None:
    """自定义 WAV 优先；否则播放选中的内置提示音。"""
    if path and os.path.isfile(path) and _play_file(path):
        return
    play_builtin(name)


def sit_sound(name: str = "sit_soft") -> None:
    play_builtin(name)


def stand_sound(name: str = "stand_up") -> None:
    play_builtin(name)


def soft_tick() -> None:
    play_builtin("dingdong")
