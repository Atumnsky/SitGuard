"""重新生成最终界面截图（主界面/休息弹窗/设置）。"""
import ctypes
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

from PIL import Image

import ctypes as _ct
try:
    _u = _ct.windll.user32
    _u.SetProcessDpiAwarenessContext.argtypes = [_ct.c_void_p]
    _u.SetProcessDpiAwarenessContext.restype = _ct.c_bool
    _u.SetProcessDpiAwarenessContext(_ct.c_void_p(-4))
except Exception:
    pass
ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
OUT = ROOT / "screenshots"
user32 = ctypes.windll.user32
gdi = ctypes.windll.gdi32
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int


def windows_of(pid):
    out = []
    EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @EnumProc
    def cb(hwnd, lp):
        wpid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
        if wpid.value == pid:
            n = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            r = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            out.append({"hwnd": hwnd, "title": buf.value,
                        "rect": (r.left, r.top, r.right, r.bottom)})
        return True

    user32.EnumWindows(cb, 0)
    return out


def capture(hwnd, path):
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    hdc = user32.GetWindowDC(hwnd)
    memdc = gdi.CreateCompatibleDC(hdc)
    bmp = gdi.CreateCompatibleBitmap(hdc, w, h)
    gdi.SelectObject(memdc, bmp)
    user32.PrintWindow(hwnd, memdc, 2)

    class BIH(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                    ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    bi = BIH()
    bi.biSize = ctypes.sizeof(BIH)
    bi.biWidth, bi.biHeight = w, -h
    bi.biPlanes, bi.biBitCount = 1, 32
    raw = ctypes.create_string_buffer(w * h * 4)
    gdi.GetDIBits(memdc, bmp, 0, h, raw, ctypes.byref(bi), 0)
    Image.frombuffer("RGB", (w, h), raw, "raw", "BGRX", 0, 1).save(path)
    gdi.DeleteObject(bmp)
    gdi.DeleteDC(memdc)
    user32.ReleaseDC(hwnd, hdc)
    return w, h


def launch(extra_env):
    env = dict(os.environ)
    env.update(extra_env)
    return subprocess.Popen([PY, str(ROOT / "main.py"), "--demo"], cwd=str(ROOT),
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def stop(proc):
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def main():
    OUT.mkdir(exist_ok=True)
    base = {"SITGUARD_OVERRIDE": json.dumps({"demo_mode": True, "sound": True, "language": "zh"}),
            "SITGUARD_FAKE_SIT": "1613",
            "SITGUARD_ALLOW_MULTI": "1"}

    # 主界面
    p = launch(base)
    try:
        time.sleep(7)
        wins = windows_of(p.pid)
        main_win = next((w for w in wins if w["title"].startswith("SitGuard")
                         and w["rect"][2] - w["rect"][0] < 1000), None)
        if main_win:
            capture(main_win["hwnd"], OUT / "main.png")
            print("main ok")
    finally:
        stop(p)

    # 休息弹窗
    p = launch({**base, "SITGUARD_FAKE_SIT": "2700", "SITGUARD_AUTOTEST": "2500"})
    try:
        time.sleep(7)
        wins = windows_of(p.pid)
        overlay = next((w for w in wins if w["rect"][2] - w["rect"][0] >= 1400), None)
        if overlay:
            capture(overlay["hwnd"], OUT / "break_overlay.png")
            print("overlay ok")
    finally:
        stop(p)

    # 设置
    p = launch({**base, "SITGUARD_OPEN_SETTINGS": "2500"})
    try:
        time.sleep(6)
        wins = windows_of(p.pid)
        settings = next((w for w in wins if "设置" in w["title"]), None)
        if settings:
            capture(settings["hwnd"], OUT / "settings.png")
            print("settings ok")
    finally:
        stop(p)


if __name__ == "__main__":
    main()
