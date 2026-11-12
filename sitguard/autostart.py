"""Windows 开机自启（启动文件夹快捷方式）。

用随附的 MakeShortcut.vbs 创建快捷方式：VBScript 对中文路径更稳，
且不会弹出 PowerShell 窗口。
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

log = logging.getLogger("sitguard.autostart")

SHORTCUT_NAME = "SitGuard.lnk"      # 用 ASCII 文件名，避免 VBScript 处理中文路径的编码问题
SCRIPT_NAME = "MakeShortcut.vbs"


def startup_dir() -> Path:
    appdata = os.environ.get("APPDATA", "")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def shortcut_path() -> Path:
    return startup_dir() / SHORTCUT_NAME


def _run_make_shortcut(action: str) -> bool:
    app_dir = Path(__file__).resolve().parent.parent
    script = app_dir / SCRIPT_NAME
    if not script.exists():
        log.warning("缺少 %s，无法创建快捷方式", script)
        return False
    cscript = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "cscript.exe"
    cmd = [str(cscript), "//nologo", str(script), action, str(shortcut_path())]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if proc.returncode != 0:
            log.warning("快捷方式脚本失败：%s %s", proc.returncode, proc.stderr.strip())
        return proc.returncode == 0
    except Exception as exc:  # noqa: BLE001
        log.warning("设置开机自启失败：%s", exc)
        return False


def is_enabled() -> bool:
    return shortcut_path().exists()


def set_enabled(enabled: bool) -> bool:
    """创建或删除启动快捷方式，成功返回 True。"""
    path = shortcut_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not enabled:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            if path.exists():
                _run_make_shortcut("delete")
            return not path.exists()
        _run_make_shortcut("create")
        return path.exists()
    except Exception as exc:  # noqa: BLE001
        log.warning("设置开机自启失败：%s", exc)
        return False

