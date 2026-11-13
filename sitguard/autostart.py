"""Windows 开机自启。

优先写入 HKCU\\...\\Run（比启动文件夹更可靠，不依赖 Explorer 启动项状态），
同时清理由旧版本创建的启动文件夹快捷方式，避免重复启动。
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import winreg
from pathlib import Path

log = logging.getLogger("sitguard.autostart")

SHORTCUT_NAME = "SitGuard.lnk"
SCRIPT_NAME = "MakeShortcut.vbs"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "SitGuard"


def startup_dir() -> Path:
    appdata = os.environ.get("APPDATA", "")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def shortcut_path() -> Path:
    return startup_dir() / SHORTCUT_NAME


def _command() -> str:
    exe = Path(sys.executable)
    if exe.name.lower() == "python.exe":
        pythonw = exe.with_name("pythonw.exe")
        if pythonw.exists():
            exe = pythonw
    main = Path(__file__).resolve().parent.parent / "main.py"
    return f'"{exe}" "{main}" --minimized'


def _read_run() -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, RUN_VALUE)
            return str(value)
    except FileNotFoundError:
        return None
    except OSError as exc:
        log.warning("读取开机自启注册表失败：%s", exc)
        return None


def _write_run(command: str) -> bool:
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                                winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, command)
        return True
    except OSError as exc:
        log.warning("写入开机自启注册表失败：%s", exc)
        return False


def _remove_run() -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, RUN_VALUE)
    except FileNotFoundError:
        pass
    except OSError as exc:
        log.warning("删除开机自启注册表失败：%s", exc)


def _run_make_shortcut(action: str) -> bool:
    app_dir = Path(__file__).resolve().parent.parent
    script = app_dir / SCRIPT_NAME
    if not script.exists():
        return False
    cscript = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "cscript.exe"
    cmd = [str(cscript), "//nologo", str(script), action, str(shortcut_path())]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return proc.returncode == 0
    except Exception:  # noqa: BLE001
        return False


def is_enabled() -> bool:
    return bool(_read_run())


def set_enabled(enabled: bool) -> bool:
    """写入/删除 HKCU Run 注册表项；成功返回 True。"""
    if not enabled:
        _remove_run()
        try:
            shortcut_path().unlink(missing_ok=True)
        except OSError:
            pass
        return not _read_run()
    command = _command()
    ok = _write_run(command)
    if ok:
        # 清掉旧版启动文件夹快捷方式，避免登录时启动两份
        try:
            shortcut_path().unlink(missing_ok=True)
        except OSError:
            pass
    return ok and _read_run() == command


def ensure_enabled() -> bool:
    """配置要求自启但注册表缺失/过期时自动修复。"""
    current = _read_run()
    if current == _command():
        return True
    return set_enabled(True)
