"""SitGuard 启动入口。"""

from __future__ import annotations

import ctypes
import json
import logging
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sitguard.app import App, enable_dpi_awareness, setup_logging  # noqa: E402
from sitguard.config import load_config, save_config  # noqa: E402

MUTEX_NAME = "Global\\SitGuard.SingleInstance.v1"
log = logging.getLogger("sitguard.main")


def acquire_single_instance():
    """返回 (mutex_handle, already_running)。句柄需保持存活。"""
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
        ERROR_ALREADY_EXISTS = 183
        if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            return handle, True
        return handle, False
    except Exception:  # noqa: BLE001
        return None, False


def main() -> int:
    # 必须在创建 Tk 之前设置 DPI 感知，否则界面会被系统位图拉伸而发虚
    enable_dpi_awareness()
    setup_logging()
    args = [a.lower() for a in sys.argv[1:]]
    demo = "--demo" in args
    minimized = "--minimized" in args
    # 调试用：SITGUARD_OVERRIDE 可传入 JSON 覆盖配置（如缩短计时方便测试）
    override = os.environ.get("SITGUARD_OVERRIDE", "")
    if override:
        try:
            cfg = load_config()
            for key, value in json.loads(override).items():
                if hasattr(cfg, key):
                    setattr(cfg, key, value)
            save_config(cfg.normalized())
            log.info("已应用调试配置覆盖：%s", override)
        except Exception:  # noqa: BLE001
            log.exception("调试配置覆盖失败")

    handle, already = acquire_single_instance()
    if already:
        log.info("已有实例在运行，退出本次启动")
        try:
            ctypes.windll.user32.MessageBoxW(
                None, "SitGuard 已经在运行了（请看屏幕右下角托盘图标）。", "SitGuard", 0x40
            )
        except Exception:  # noqa: BLE001
            pass
        return 0
    try:
        app = App(start_minimized=minimized, demo=demo)
        app.root.mainloop()
    except Exception:
        log.exception("程序异常退出")
        logging.shutdown()
        try:
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
        except Exception:  # noqa: BLE001
            pass
        return 1
    logging.shutdown()
    try:
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
    except Exception:  # noqa: BLE001
        pass
    # 托盘/摄像头线程可能残留，直接结束进程，避免“关了窗口进程还在”
    os._exit(0)


if __name__ == "__main__":
    sys.exit(main())
