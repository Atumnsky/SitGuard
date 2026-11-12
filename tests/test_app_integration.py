"""集成测试：真实 App/Tk 窗口，验证弹窗、姿态、设置、摄像头开关。"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["SITGUARD_OVERRIDE"] = json.dumps({"demo_mode": True, "sound": False})

from sitguard.app import App  # noqa: E402
from sitguard.engine import Phase  # noqa: E402
from sitguard.posture import PostureProfile  # noqa: E402

OUT = ROOT / "integration_result.txt"
OUT.write_text("", encoding="utf-8")


def log(line: str) -> None:
    print(line, flush=True)
    with OUT.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    log(("PASS" if cond else "FAIL") + " | " + name + " | " + str(detail))


log("creating app...")
app = App(demo=True)
log("app created")
root = app.root


def step(fn, label):
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        import traceback

        log(f"EXCEPTION in {label}: {exc}")
        log(traceback.format_exc())


def s1():
    app.show_window()
    root.update()
    check("main window visible", root.state() != "withdrawn", root.state())
    check("scale configured", app.scale >= 1.0, app.scale)


def s2():
    app.test_break()
    root.update()
    check("overlay opened", app.overlay.win is not None)
    check("engine in break", app.engine.phase is Phase.BREAK, str(app.engine.phase))


def s3():
    app.confirm_break()
    root.update()
    app._drain_tasks()
    root.update()
    check("overlay closed by confirm", app.overlay.win is None)
    check("break finished", app.engine.phase is Phase.WATCHING, str(app.engine.phase))
    check("break counted", app.engine.stats.breaks >= 1, app.engine.stats.breaks)


def s4():
    app.toggle_standing()
    root.update()
    check("manual standing", app.engine.posture == "standing", app.engine.posture)
    app.toggle_standing()
    root.update()
    check("manual sitting", app.engine.posture in ("sitting", "unknown"), app.engine.posture)


def s5():
    app.settings_window.open()
    root.update()
    check("settings window open", app.settings_window.win is not None)
    app.settings_window.close()
    app.open_calibration()
    root.update()
    check("calibration window open", app.calibration_window.win is not None)
    app.calibration_window.close()
    app.set_calibration(
        PostureProfile(face_y=0.72, face_h=0.22, shoulder_y=0.9, visible=True),
        PostureProfile(visible=False),
    )
    check("calibration saved", bool(app.config.calibration.get("sitting")),
          app.config.calibration)


def s6():
    app.toggle_pause()
    root.update()
    check("paused", app.engine.phase is Phase.PAUSED, str(app.engine.phase))
    app.toggle_pause()
    check("resumed", app.engine.phase is Phase.WATCHING, str(app.engine.phase))


def s7():
    app.toggle_camera()
    root.update()
    check("camera disabled", app.config.camera_enabled is False)
    app.toggle_camera()
    root.update()
    check("camera re-enabled", app.config.camera_enabled is True)


def finish():
    log("finishing...")
    app.quit()
    log("app.quit returned")
    root.quit()


for i, (fn, label) in enumerate([(s1, "s1"), (s2, "s2"), (s3, "s3"), (s4, "s4"),
                                 (s5, "s5"), (s6, "s6"), (s7, "s7"), (finish, "finish")]):
    root.after(500 + i * 900, lambda fn=fn, label=label: step(fn, label))

log("entering mainloop")
root.mainloop()
ok = all(r[1] for r in results)
log("SUMMARY: " + ("ALL PASS" if ok else "FAILURES"))
log("RESULTS: " + json.dumps(results, ensure_ascii=False))

# pystray 的守护线程可能让解释器不退出，测试结束时强制结束
os._exit(0)
