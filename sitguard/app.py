"""应用主控制器：把引擎、摄像头、界面、托盘串起来。"""

from __future__ import annotations

import ctypes
import json
import logging
import os
import queue
import sys
import threading
import time
import tkinter as tk
from pathlib import Path

from . import autostart, i18n, sound, ui
from .camera import CameraSnapshot, CameraWorker, SimulatedCamera
from .config import Config, data_dir, load_config, save_config, stats_path
from .engine import EngineEvent, Phase, SessionEngine, Snapshot
from .posture import Posture, PostureProfile
from .views import BreakOverlay, CalibrationWindow, MainWindow, SettingsWindow

log = logging.getLogger("sitguard.app")

POLL_MS = 200          # 主循环刷新间隔
PREVIEW_MS = 280       # 预览帧刷新间隔
STATS_SAVE_SECONDS = 30.0


class App:
    def __init__(self, start_minimized: bool = False, demo: bool = False):
        self.config = load_config()
        i18n.set_language(self.config.language)
        if demo:
            self.config.demo_mode = True
        self.start_minimized = start_minimized
        self.engine = SessionEngine(self.config)
        self.engine.add_listener(self._on_engine_event)
        self._stats_loaded = self._load_today_stats()
        # 演示/截图用：预置久坐秒数，省去等待
        fake_sit = os.environ.get("SITGUARD_FAKE_SIT")
        if fake_sit:
            try:
                seconds = float(fake_sit)
                self.engine.sitting_seconds = seconds
                self.engine.stats.sitting_seconds = seconds
            except ValueError:
                pass

        self.root = tk.Tk()
        self.root.withdraw()
        # 高 DPI：按真实 DPI 设定缩放，之后所有 dp() 尺寸和字体都跟着放大
        try:
            dpi = float(self.root.winfo_fpixels("1i"))
        except tk.TclError:
            dpi = 96.0
        self.scale = ui.configure_scale(dpi, self.root)
        log.info("DPI=%.0f scale=%.2f", dpi, self.scale)
        self._apply_window_style()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.main = MainWindow(self, self.root)
        self.settings_window = SettingsWindow(self, self.root)
        self.calibration_window = CalibrationWindow(self, self.root)
        self.overlay = BreakOverlay(self, self.root)

        self.camera: CameraWorker | SimulatedCamera | None = None
        self._camera_snapshot = CameraSnapshot()
        self._camera_message = ""
        self._camera_state = "init"
        self.manual_posture: Posture | None = None

        self._paused_by_user = False
        self._quitting = False
        self._camera_error_since: float | None = None
        self._last_camera_restart = 0.0
        self._last_camera_notice = 0.0
        self._last_stats_save = time.monotonic()
        self._last_preview = 0.0
        self._tray = None
        self._tasks: "queue.Queue[callable]" = queue.Queue()

        self._new_camera()
        self.engine.start()
        self.root.after(10, self._boot)

    # ------------------------------------------------------------------
    # 启动
    # ------------------------------------------------------------------
    def _apply_window_style(self) -> None:
        self.root.title(i18n.t("app_title"))
        try:
            self.root.iconbitmap(default=str(Path(__file__).parent / "assets" / "sitguard.ico"))
        except tk.TclError:
            pass
        self.root.configure(bg=ui.BG)
        self.root.attributes("-topmost", bool(self.config.always_on_top))

    def _boot(self) -> None:
        self._setup_tray()
        if not self.start_minimized:
            self.show_window()
        else:
            # 静默启动：任务栏保留图标，确保用户随时能找到它
            self.root.deiconify()
            self.root.iconify()
        self.root.after(POLL_MS, self._poll)
        log.info("SitGuard 已启动（demo=%s）", self.config.demo_mode)
        if (self.config.posture_enabled and not self.config.calibration
                and not self.config.demo_mode):
            self.root.after(2500, lambda: self.main.show_toast(
                i18n.t("toast_cal_prompt"), ui.ACCENT, ms=6000))
        if os.environ.get("SITGUARD_AUTOTEST"):
            delay = int(os.environ.get("SITGUARD_AUTOTEST", "3000") or 3000)
            self.root.after(delay, self.test_break)
        if os.environ.get("SITGUARD_OPEN_SETTINGS"):
            delay = int(os.environ.get("SITGUARD_OPEN_SETTINGS", "3000") or 3000)
            self.root.after(delay, self.open_settings)
        if os.environ.get("SITGUARD_OPEN_CALIBRATION"):
            delay = int(os.environ.get("SITGUARD_OPEN_CALIBRATION", "3000") or 3000)
            self.root.after(delay, self.open_calibration)
        if os.environ.get("SITGUARD_AUTO_QUIT"):
            delay = int(os.environ.get("SITGUARD_AUTO_QUIT", "5000") or 5000)
            self.root.after(delay, self.quit)

    def show_window(self) -> None:
        self.root.deiconify()
        self.root.lift()
        try:
            self.root.attributes("-topmost", bool(self.config.always_on_top))
        except tk.TclError:
            pass
        self.root.focus_force()
        ui.center_window(self.root, ui.dp(420), ui.dp(524), anchor="topright")

    def hide_window(self) -> None:
        if self._tray is None:
            self.root.iconify()
            return
        self.root.withdraw()
        if self.config.sound:
            pass

    def on_close(self) -> None:
        if self.config.minimize_to_tray and self._tray is not None:
            self.root.withdraw()
            self.main.show_toast(i18n.t("toast_tray"), ui.ACCENT)
            return
        self.quit()

    def quit(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        try:
            self._save_stats()
            save_config(self.config)
        except Exception:  # noqa: BLE001
            pass
        try:
            if self.camera:
                self.camera.stop()
        except Exception:  # noqa: BLE001
            pass
        # 托盘停止可能阻塞（Windows 消息循环），放到后台线程，不阻塞界面退出
        if self._tray is not None:
            tray = self._tray
            self._tray = None
            threading.Thread(target=self._stop_async, args=(tray,), daemon=True).start()
        try:
            self.overlay.close()
            self.root.destroy()
        except tk.TclError:
            pass

    @staticmethod
    def _stop_async(target) -> None:
        try:
            target.stop()
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------
    # 摄像头
    # ------------------------------------------------------------------
    def _new_camera(self) -> None:
        if self.camera is not None:
            try:
                self.camera.stop()
            except Exception:  # noqa: BLE001
                pass
            self.camera = None
        self._start_camera()

    def _start_camera(self) -> None:
        if not self.config.camera_enabled:
            self._camera_state = "off"
            self._camera_message = i18n.t("camera_off_msg")
            return
        if self.config.demo_mode:
            cam = SimulatedCamera(self.config, on_presence=self._on_presence,
                                  on_posture=self._on_posture)
        else:
            cam = CameraWorker(self.config, on_presence=self._on_presence,
                               on_posture=self._on_posture)
        self.camera = cam
        self._camera_state = "init"
        self._camera_error_since = None
        cam.start()
        if self.manual_posture:
            try:
                cam.posture.set_manual(self.manual_posture, time.monotonic())
            except Exception:  # noqa: BLE001
                pass

    def _camera_watchdog(self, now: float, snap: CameraSnapshot) -> None:
        """长时间运行/驱动掉线时自动重启摄像头，避免必须手动开关。"""
        if not self.config.camera_enabled or self.camera is None:
            self._camera_error_since = None
            return
        state = snap.status.state
        if state == "error":
            if self._camera_error_since is None:
                self._camera_error_since = now
            if (now - self._camera_error_since > 12.0
                    and now - self._last_camera_restart > 25.0):
                self._recover_camera(now, "连续打开失败")
        elif state == "ok":
            self._camera_error_since = None
            # 画面 8 秒没有新帧：线程可能卡死或设备被系统挂起
            if (snap.stamp and now - snap.stamp > 8.0
                    and now - self._last_camera_restart > 25.0):
                self._recover_camera(now, "画面停止更新")
        else:
            self._camera_error_since = None

    def _recover_camera(self, now: float, reason: str) -> None:
        self._last_camera_restart = now
        log.warning("摄像头自动恢复：%s", reason)
        if now - self._last_camera_notice > 60.0:
            self._last_camera_notice = now
            self.notify(i18n.t("toast_camera_recover"), ui.WARN)
        old = self.camera
        self.camera = None
        if old is not None:
            # 释放旧设备可能阻塞，放到后台线程，避免界面卡住
            threading.Thread(target=self._stop_async, args=(old,), daemon=True).start()
        self._start_camera()

    def _on_presence(self, seen: bool, when: float) -> None:
        # 摄像头线程调用
        self.engine.notify_presence(seen, when)

    def _on_posture(self, posture: Posture, when: float) -> None:
        # 摄像头线程调用
        if self.manual_posture:
            return
        self.engine.notify_posture(posture, when)

    def toggle_standing(self) -> None:
        """手动切换坐/站（姿态检测看不清身体时使用）。"""
        if self.manual_posture == "standing":
            self.manual_posture = "sitting"
            msg = i18n.t("toast_sitting")
        else:
            self.manual_posture = "standing"
            msg = i18n.t("toast_standing")
        self.engine.set_posture_manual(self.manual_posture)
        try:
            if self.camera is not None:
                self.camera.posture.set_manual(self.manual_posture, time.monotonic())
        except Exception:  # noqa: BLE001
            pass
        self.notify(msg, ui.GOOD if self.manual_posture == "standing" else ui.TEXT_DIM)

    def toggle_camera(self) -> None:
        self.config.camera_enabled = not self.config.camera_enabled
        if not self.config.camera_enabled:
            self.engine.tracker.reset()
            self.engine.present = False
            self._camera_state = "off"
            if self.camera:
                self.camera.stop()
            self.camera = None
            self.main.set_camera_button(False)
            self.notify(i18n.t("toast_cam_off"), ui.WARN)
        else:
            self.main.set_camera_button(True)
            self._new_camera()
            self.notify(i18n.t("toast_cam_on"), ui.GOOD)
        save_config(self.config)

    def toggle_demo(self) -> None:
        self.config.demo_mode = not self.config.demo_mode
        save_config(self.config)
        self._new_camera()
        self.notify(i18n.t("toast_demo_on") if self.config.demo_mode else i18n.t("toast_demo_off"), ui.ACCENT)

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------
    def _poll(self) -> None:
        if self._quitting:
            return
        try:
            self._drain_tasks()
            now = time.monotonic()
            if self.camera is not None:
                snap = self.camera.snapshot()
                self._camera_snapshot = snap
                status = snap.status
                if status.state == "ok":
                    self._camera_state = "ok"
                    self._camera_message = ""
                elif status.state == "error":
                    self._camera_state = "error"
                    self._camera_message = status.message
                elif status.state == "off":
                    self._camera_state = "off"
                    self._camera_message = status.message
            self._camera_watchdog(now, self._camera_snapshot)
            self.engine.tick(now)
            try:
                view = bool(self.root.winfo_exists()) and self.root.state() != "withdrawn"
            except tk.TclError:
                return
            if view:
                self._refresh(now)
            if self.overlay.win is not None:
                self._refresh_overlay()
            self._auto_save_stats(now)
        except Exception:  # noqa: BLE001
            log.exception("主循环异常")
        finally:
            if not self._quitting:
                try:
                    self.root.after(POLL_MS, self._poll)
                except tk.TclError:
                    pass

    def _refresh(self, now: float) -> None:
        pose_ok = self._camera_snapshot.status.pose_ok
        snap = self.engine.snapshot(self._camera_state, self._camera_message, pose_ok)
        self.main.refresh(snap, self._camera_state)
        if now - self._last_preview >= PREVIEW_MS / 1000.0:
            self._last_preview = now
            self.main.update_preview(self._camera_snapshot, self.engine.present)

    def _refresh_overlay(self) -> None:
        pose_ok = self._camera_snapshot.status.pose_ok
        snap = self.engine.snapshot(self._camera_state, self._camera_message, pose_ok)
        self.overlay.update(snap, self._camera_snapshot)

    # ------------------------------------------------------------------
    # 引擎事件
    # ------------------------------------------------------------------
    def _on_engine_event(self, ev: EngineEvent) -> None:
        # 事件可能来自摄像头线程，统一投递到 Tk 主线程
        self._post(lambda: self._handle_event(ev))

    def _handle_event(self, ev: EngineEvent) -> None:
        if ev.kind == "break_start":
            self.show_window()
            self.overlay.show(self.engine.break_total_seconds, ev.detail)
            if self.config.sound:
                for i in range(max(1, self.config.sound_repeat)):
                    self.root.after(i * 700, sound.reminder_sound)
            self.main.show_toast(i18n.t("toast_break_start"), ui.WARN, ms=4000)
        elif ev.kind == "break_end":
            self.overlay.close()
            key, _, num = (ev.detail or "timeout").partition(":")
            if key == "standing":
                detail = i18n.t("break_end_standing", n=int(num or 0))
            elif key == "gone":
                detail = i18n.t("break_end_gone", n=int(num or 0))
            elif key == "manual":
                detail = i18n.t("break_end_manual")
            else:
                detail = i18n.t("break_end_timeout")
            self.main.show_toast(i18n.t("toast_break_end", d=detail), ui.GOOD, ms=3500)
            if self.config.sound:
                sound.soft_tick()
            self._save_stats()
        elif ev.kind == "break_follow":
            if self.config.sound:
                sound.reminder_sound()
        elif ev.kind == "away":
            if self.engine.phase is Phase.WATCHING:
                self.main.show_toast(i18n.t("toast_away"), ui.TEXT_DIM, ms=1800)
        elif ev.kind == "reset_by_break":
            self.main.show_toast(i18n.t("toast_reset_break"), ui.GOOD, ms=2500)
        elif ev.kind == "reset_by_standing":
            self.main.show_toast(i18n.t("toast_reset_standing"), ui.GOOD, ms=2500)
        elif ev.kind == "snoozed":
            self.overlay.close()
            self.main.show_toast(i18n.t("toast_snoozed", m=ev.detail), ui.TEXT_DIM, ms=2500)

    # ------------------------------------------------------------------
    # 用户操作
    # ------------------------------------------------------------------
    def toggle_pause(self) -> None:
        if self.engine.phase is Phase.PAUSED:
            self.engine.resume()
            self.notify(i18n.t("toast_resumed"), ui.GOOD)
        else:
            self.engine.pause()
            self.notify(i18n.t("toast_paused"), ui.WARN)

    def test_break(self) -> None:
        self.engine.force_break()
        self.overlay.show(self.engine.break_total_seconds, i18n.t("test_reminder"))

    def confirm_break(self) -> None:
        """用户在弹窗上点“我站起来了 / 关闭本次提醒”。"""
        if self.engine.phase is not Phase.BREAK:
            return
        self.engine.confirm_break()
        self._save_stats()

    def snooze_break(self) -> None:
        self.engine.snooze()
        self._save_stats()

    def open_settings(self) -> None:
        self.settings_window.open()

    def open_calibration(self) -> None:
        self.calibration_window.show()

    def set_language(self, language: str) -> None:
        """切换界面语言并即时重建界面。"""
        lang = "en" if str(language).lower().startswith("en") else "zh"
        if lang == getattr(self.config, "language", "zh"):
            return
        self.config.language = lang
        i18n.set_language(lang)
        save_config(self.config)
        try:
            self.settings_window.close()
            self.calibration_window.close()
            if self.overlay.win is not None:
                self.overlay.close()
            for child in list(self.root.winfo_children()):
                child.destroy()
            self.main = MainWindow(self, self.root)
            self.main.set_camera_button(self.config.camera_enabled)
            self._apply_window_style()
            self._setup_tray()
            self.root.after(150, lambda: self.notify(i18n.t("language_changed"), ui.GOOD))
        except Exception:  # noqa: BLE001
            log.exception("切换语言失败")

    def set_calibration(self, sitting: PostureProfile,
                        standing: PostureProfile) -> None:
        self.config.calibration = {
            "sitting": sitting.to_dict(),
            "standing": standing.to_dict(),
        }
        self.config.posture_enabled = True
        save_config(self.config)
        try:
            if self.camera is not None and hasattr(self.camera, "posture"):
                self.camera.posture.set_calibration(sitting, standing)
        except Exception:  # noqa: BLE001
            log.exception("应用校准失败")

    def apply_settings(self) -> None:
        old = self.config.copy()
        self.config = self.config.normalized()
        self.engine.config = self.config
        self.engine.tracker.present_seconds = self.config.present_seconds
        self.engine.tracker.away_seconds = self.config.away_seconds
        try:
            self.root.attributes("-topmost", bool(self.config.always_on_top))
        except tk.TclError:
            pass
        if self.config.autostart != old.autostart:
            ok = autostart.set_enabled(self.config.autostart)
            if not ok:
                self.config.autostart = old.autostart
                self.notify(i18n.t("toast_autostart_fail"), ui.DANGER)
        if (self.config.camera_index != old.camera_index
                or self.config.camera_enabled != old.camera_enabled
                or self.config.demo_mode != old.demo_mode
                or self.config.posture_enabled != old.posture_enabled
                or self.config.pose_model != old.pose_model):
            self._new_camera()
            self.main.set_camera_button(self.config.camera_enabled)
        save_config(self.config)

    def notify(self, text: str, color: str = ui.ACCENT) -> None:
        try:
            self.main.show_toast(text, color)
        except tk.TclError:
            pass

    def _post(self, fn) -> None:
        self._tasks.put(fn)

    def _drain_tasks(self) -> None:
        while True:
            try:
                fn = self._tasks.get_nowait()
            except queue.Empty:
                return
            try:
                fn()
            except Exception:  # noqa: BLE001
                log.exception("任务执行失败")

    # ------------------------------------------------------------------
    # 统计与托盘
    # ------------------------------------------------------------------
    def _load_today_stats(self) -> bool:
        try:
            raw = json.loads(stats_path().read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            return False
        today = time.strftime("%Y-%m-%d")
        if raw.get("date") == today:
            st = self.engine.stats
            st.sitting_seconds = float(raw.get("sitting_seconds", 0.0))
            st.breaks = int(raw.get("breaks", 0))
            st.reminders = int(raw.get("reminders", 0))
            return True
        return False

    def _save_stats(self) -> None:
        self._last_stats_save = time.monotonic()
        st = self.engine.stats
        payload = {
            "date": st.date,
            "sitting_seconds": round(st.sitting_seconds, 1),
            "breaks": st.breaks,
            "reminders": st.reminders,
        }
        try:
            path = stats_path()
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            path.unlink(missing_ok=True)
            tmp.replace(path)
        except OSError as exc:
            log.debug("保存统计失败：%s", exc)

    def _auto_save_stats(self, now: float) -> None:
        if now - self._last_stats_save >= STATS_SAVE_SECONDS:
            self._save_stats()

    def _setup_tray(self) -> None:
        if self._tray is not None:
            old = self._tray
            self._tray = None
            threading.Thread(target=self._stop_async, args=(old,), daemon=True).start()
        try:
            import pystray
            from PIL import Image
        except Exception:  # noqa: BLE001
            log.info("pystray 不可用，使用普通窗口模式")
            return
        try:
            image = Image.open(Path(__file__).parent / "assets" / "sitguard.png")
            image.load()
        except Exception:  # noqa: BLE001
            return

        def show(_icon=None, _item=None):
            self._post(self.show_window)

        def quit_app(_icon=None, _item=None):
            self._post(self.quit)

        def toggle(_icon=None, _item=None):
            self._post(self.toggle_pause)

        def toggle_cam(_icon=None, _item=None):
            self._post(self.toggle_camera)

        def take_break(_icon=None, _item=None):
            self._post(self.test_break)

        menu = pystray.Menu(
            pystray.MenuItem(i18n.t("tray_open"), show, default=True),
            pystray.MenuItem(i18n.t("tray_pause"), toggle),
            pystray.MenuItem(i18n.t("tray_break"), take_break),
            pystray.MenuItem(i18n.t("tray_cam"), toggle_cam),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(i18n.t("tray_exit"), quit_app),
        )
        try:
            icon = pystray.Icon("SitGuard", image, i18n.t("tray_tip"), menu)
            icon.run_detached()
            self._tray = icon
        except Exception as exc:  # noqa: BLE001
            log.warning("托盘图标创建失败：%s", exc)
            self._tray = None


def enable_dpi_awareness() -> None:
    """开启 Per-Monitor V2 DPI 感知，让 3.5K/200% 屏上的文字与线条保持原生清晰。"""
    if sys.platform != "win32":
        return
    try:
        user32 = ctypes.windll.user32
        user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        user32.SetProcessDpiAwarenessContext.restype = ctypes.c_bool
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except Exception:  # noqa: BLE001
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:  # noqa: BLE001
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:  # noqa: BLE001
        pass


def setup_logging() -> None:
    log_dir = data_dir()
    handlers = [logging.FileHandler(log_dir / "sitguard.log", encoding="utf-8")]
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=handlers,
    )
