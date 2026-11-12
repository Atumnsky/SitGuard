"""最终验证：以真实模式（真实摄像头）启动，截图主窗口。"""
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from screenshots import capture, windows_of  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable

env = {k: v for k, v in os.environ.items() if not k.startswith("SITGUARD_")}
env["SITGUARD_ALLOW_MULTI"] = "1"
proc = subprocess.Popen([PY, str(ROOT / "main.py")], cwd=str(ROOT), env=env,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    time.sleep(14)
    wins = windows_of(proc.pid)
    main_win = next((w for w in wins if w["title"].startswith("SitGuard")
                     and 200 < w["rect"][2] - w["rect"][0] < 1000), None)
    if main_win:
        capture(main_win["hwnd"], ROOT / "screenshots" / "final_real.png")
        print("captured", main_win["rect"])
    else:
        print("no window", [(w["title"], w["rect"]) for w in wins])
        sys.exit(1)
finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
