"""截取英文界面（主界面/设置）。"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from screenshots import capture, windows_of  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
BASE = {"demo_mode": True, "sound": True, "language": "en"}
MULTI = {"SITGUARD_ALLOW_MULTI": "1"}


def run(extra, out_name, title_part=""):
    env = {k: v for k, v in os.environ.items() if not k.startswith("SITGUARD_")}
    env["SITGUARD_OVERRIDE"] = json.dumps(BASE)
    env.update(MULTI)
    env.update({k: v for k, v in extra.items() if k.startswith("SITGUARD_")})
    env["SITGUARD_FAKE_SIT"] = "1613"
    proc = subprocess.Popen([PY, str(ROOT / "main.py"), "--demo"], cwd=str(ROOT),
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(6)
        wins = windows_of(proc.pid)
        target = next((w for w in wins if title_part in w["title"]), None)
        if target:
            print(out_name, capture(target["hwnd"], ROOT / "screenshots" / out_name))
        else:
            print("not found", [(w["title"], w["rect"]) for w in wins])
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


run({}, "main_en.png", "SitGuard")
run({"SITGUARD_OPEN_SETTINGS": "2000"}, "settings_en.png", "SitGuard Settings")
