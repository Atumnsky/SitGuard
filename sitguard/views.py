"""主面板 + 休息提醒弹窗 + 设置窗口（全部支持高 DPI）。"""

from __future__ import annotations

import math
import time
import tkinter as tk

from PIL import Image, ImageDraw, ImageTk

from . import ui
from .camera import CameraSnapshot
from .engine import Phase, Snapshot
from .i18n import fmt_duration, t
from .posture import PostureProfile, median_profile


def arc_points(box: tuple[float, float, float, float], start_deg: float,
               extent_deg: float, steps: int = 72) -> list[float]:
    """把圆弧换算成折线坐标，避免 Tk 粗线圆弧在高 DPI 下的渲染问题。"""
    x1, y1, x2, y2 = box
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    rx, ry = (x2 - x1) / 2, (y2 - y1) / 2
    pts: list[float] = []
    for i in range(steps + 1):
        a = math.radians(start_deg + extent_deg * i / steps)
        pts.append(cx + rx * math.cos(a))
        pts.append(cy - ry * math.sin(a))
    return pts

# ---------------------------------------------------------------------------
# 圆环计时器
# ---------------------------------------------------------------------------


class RingMeter(tk.Canvas):
    def __init__(self, master, size: int, bg: str = ui.BG):
        super().__init__(master, width=size, height=size, bg=bg,
                         highlightthickness=0, bd=0)
        self._size = size
        self._thickness = max(6, ui.dp(13))
        self._arc = None
        self._time_item = None
        self._label_item = None
        self._sub_item = None
        self._ring_bg = None
        self._last = None
        self._build()

    def _build(self) -> None:
        s = self._size
        pad = self._thickness + ui.dp(7)
        box = (pad, pad, s - pad, s - pad)
        self._box = box
        self._ring_bg = self.create_oval(*box, outline="#2a303a", width=self._thickness)
        pts = arc_points(box, 90, -1.5)
        self._arc = self.create_line(
            *pts, fill=ui.ACCENT, width=self._thickness,
            capstyle=tk.ROUND, joinstyle=tk.ROUND, smooth=True,
        )
        self._time_item = self.create_text(s / 2, s / 2 - ui.dp(10), text="--:--",
                                           fill=ui.TEXT, font=ui.mono_font(30, "bold"),
                                           anchor="center")
        self._label_item = self.create_text(s / 2, s / 2 + ui.dp(28), text=t("sit_elapsed"),
                                            fill=ui.TEXT_DIM, font=ui.ui_font(9),
                                            anchor="center")
        self._sub_item = self.create_text(s / 2, s / 2 + ui.dp(49), text="",
                                          fill=ui.TEXT_FAINT, font=ui.ui_font(8),
                                          anchor="center")

    def update_meter(self, *, ratio: float, time_text: str, label: str, sub: str,
                     color: str, dim: bool = False) -> None:
        ratio = max(0.001, min(1.0, ratio))
        state = (round(ratio * 240), time_text, label, sub, color, dim)
        extent = max(1.5, 240 * ratio) if not dim else 0.1
        pts = arc_points(self._box, 90, -extent)
        self.coords(self._arc, *pts)
        self.itemconfigure(self._arc, fill=color,
                           state="normal" if not dim else "hidden")
        if state != self._last:
            self._last = state
            self.itemconfigure(self._time_item, text=time_text,
                               fill=ui.TEXT_FAINT if dim else ui.TEXT,
                               font=ui.mono_font(30 if len(time_text) <= 5 else 23, "bold"))
            self.itemconfigure(self._label_item, text=label,
                               fill=ui.TEXT_FAINT if dim else ui.TEXT_DIM)
            self.itemconfigure(self._sub_item, text=sub)


# ---------------------------------------------------------------------------
# 摄像头预览
# ---------------------------------------------------------------------------


class PreviewPanel(tk.Frame):
    def __init__(self, master, width: float = 208, height: float = 117, **kwargs):
        super().__init__(master, bg=ui.BG_2, highlightthickness=1,
                         highlightbackground=ui.BORDER, **kwargs)
        self._pw, self._ph = ui.dp(width), ui.dp(height)
        self.canvas = tk.Canvas(self, width=self._pw, height=self._ph, bg="#0c0e12",
                                highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self._photo = None
        self._img_item = None
        self._placeholder = self.canvas.create_text(
            self._pw / 2, self._ph / 2, text=t("preview"), fill=ui.TEXT_FAINT,
            font=ui.ui_font(9), anchor="center")
        self._badge_bg = self.canvas.create_rectangle(
            ui.dp(6), ui.dp(5), ui.dp(92), ui.dp(27), fill="#0d0f13", outline="")
        self._badge = self.canvas.create_text(ui.dp(12), ui.dp(16), text=t("badge_present"),
                                              fill=ui.GOOD, font=ui.ui_font(8), anchor="w")

    def update_frame(self, snap: CameraSnapshot, present: bool) -> None:
        frame = snap.frame
        if frame is None:
            self.canvas.itemconfigure(self._placeholder, state="normal", text=t("preview_wait"))
            return
        try:
            img = Image.fromarray(frame[:, :, ::-1]).convert("RGB")
            img = img.resize((self._pw, self._ph), Image.BILINEAR)
        except Exception:  # noqa: BLE001
            return
        if snap.faces:
            draw = ImageDraw.Draw(img)
            sx = self._pw / frame.shape[1]
            sy = self._ph / frame.shape[0]
            for x, y, w, h, _score in snap.faces:
                color = (104, 211, 145) if present else (246, 173, 85)
                draw.rectangle([x * sx, y * sy, (x + w) * sx, (y + h) * sy],
                               outline=color, width=max(1, ui.dp(1)))
        self._photo = ImageTk.PhotoImage(img)
        self.canvas.itemconfigure(self._placeholder, state="hidden")
        if self._img_item is None:
            self._img_item = self.canvas.create_image(0, 0, image=self._photo, anchor="nw")
        else:
            self.canvas.itemconfigure(self._img_item, image=self._photo)
        self.canvas.tag_raise(self._badge_bg)
        self.canvas.tag_raise(self._badge)
        if snap.posture == "standing":
            self.canvas.itemconfigure(self._badge, text=t("badge_standing"), fill=ui.GOOD)
        elif snap.posture == "sitting":
            self.canvas.itemconfigure(self._badge, text=t("badge_sitting"), fill=ui.GOOD)
        elif present:
            self.canvas.itemconfigure(self._badge, text=t("badge_present"), fill=ui.GOOD)
        else:
            self.canvas.itemconfigure(self._badge, text=t("badge_away"), fill=ui.WARN)

    def set_offline(self, message: str) -> None:
        self.canvas.itemconfigure(self._placeholder, state="normal", text=t("preview_off"))
        self.canvas.itemconfigure(self._badge, text=t("badge_off"), fill=ui.TEXT_FAINT)


# ---------------------------------------------------------------------------
# 主面板
# ---------------------------------------------------------------------------


class MainWindow:
    """主界面：可自由缩放；小于设计尺寸时自动切成“只剩计时器”的迷你模式。"""

    DESIGN_W = 420
    DESIGN_H = 524

    def __init__(self, app, root: tk.Tk):
        self.app = app
        self.root = root
        root.title(t("app_title"))
        root.configure(bg=ui.BG)
        root.resizable(True, True)
        root.minsize(ui.dp(150), ui.dp(150))

        cfg = app.config
        w = max(ui.dp(150), ui.dp(int(getattr(cfg, "window_width", 420))))
        h = max(ui.dp(150), ui.dp(int(getattr(cfg, "window_height", 524))))
        ui.center_window(root, w, h, anchor="topright")

        self.stage = tk.Frame(root, bg=ui.BG)
        self.stage.pack(fill="both", expand=True)
        self.full = tk.Frame(self.stage, bg=ui.BG,
                             width=ui.dp(self.DESIGN_W), height=ui.dp(self.DESIGN_H))
        self.full.pack_propagate(False)
        self.mini = tk.Canvas(self.stage, bg=ui.BG, highlightthickness=0, bd=0)
        self.mini.bind("<Double-Button-1>", lambda _e: self.restore_size())

        self._mode: str | None = None
        self._layout_job = None
        self._layout_after = None
        self._last_snap: Snapshot | None = None
        self._last_camera_state = "init"
        self._last_present = False
        self._dpi = ui.DPI
        self._toast_after = None

        self._fonts = {
            "small": ui.ui_font(9),
            "tiny": ui.ui_font(8),
            "num": ui.ui_font(14, "bold"),
        }
        self._build_full()
        self.toast = tk.Label(self.stage, text="", fg="#06211f", bg=ui.ACCENT,
                              font=ui.ui_font(9, "bold"), padx=ui.dp(14), pady=ui.dp(6))
        self.toast.place_forget()

        self._bind_id = root.bind("<Configure>", self._on_configure, add="+")
        self.root.after(60, self._layout)

    # ---- 窗口尺寸 / 模式 ----
    def _on_configure(self, event) -> None:
        if event.widget is not self.root:
            return
        try:
            dpi = float(self.root.winfo_fpixels("1i"))
        except tk.TclError:
            dpi = self._dpi
        if abs(dpi - self._dpi) > 6:
            # 跨屏 DPI 变化：按新 DPI 重建，避免 Tk 把窗口“拉伸”
            self._dpi = dpi
            ui.configure_scale(dpi, self.root)
            self.root.minsize(ui.dp(150), ui.dp(150))
            self._rebuild_full()
        if self._layout_job is not None:
            try:
                self.root.after_cancel(self._layout_job)
            except tk.TclError:
                pass
        self._layout_job = self.root.after(80, self._layout)

    def _rebuild_full(self) -> None:
        try:
            self.full.destroy()
        except tk.TclError:
            pass
        self.full = tk.Frame(self.stage, bg=ui.BG,
                             width=ui.dp(self.DESIGN_W), height=ui.dp(self.DESIGN_H))
        self.full.pack_propagate(False)
        self._fonts = {
            "small": ui.ui_font(9),
            "tiny": ui.ui_font(8),
            "num": ui.ui_font(14, "bold"),
        }
        self._build_full()
        self._mode = None
        self._layout()

    def destroy(self) -> None:
        if self._layout_job:
            try:
                self.root.after_cancel(self._layout_job)
            except tk.TclError:
                pass
            self._layout_job = None
        try:
            self.root.unbind("<Configure>", self._bind_id)
        except tk.TclError:
            pass

    def _layout(self) -> None:
        self._layout_job = None
        try:
            if not self.stage.winfo_exists():
                return
        except tk.TclError:
            return
        w = self.stage.winfo_width()
        h = self.stage.winfo_height()
        if w <= 1 or h <= 1:
            self.root.after(40, self._layout)
            return
        full_w, full_h = ui.dp(self.DESIGN_W), ui.dp(self.DESIGN_H)
        if w >= full_w - 2 and h >= full_h - 2:
            if self._mode != "full":
                self.mini.place_forget()
                self._mode = "full"
            self.full.place(relx=0.5, rely=0.5, anchor="center",
                            width=full_w, height=full_h)
            if self._last_snap is not None:
                self._refresh_full(self._last_snap, self._last_camera_state)
        else:
            if self._mode != "mini":
                self.full.place_forget()
                self._mode = "mini"
            self.mini.place(x=0, y=0, relwidth=1, relheight=1)
            self._draw_mini()

    def restore_size(self) -> None:
        ui.center_window(self.root, ui.dp(self.DESIGN_W), ui.dp(self.DESIGN_H),
                         anchor="topright")
        self.root.after(50, self._layout)

    # ---- 完整布局 ----
    def _build_full(self) -> None:
        parent = self.full
        top = tk.Frame(parent, bg=ui.BG, height=ui.dp(52))
        top.pack(fill="x", padx=ui.dp(18), pady=(ui.dp(12), 0))
        top.pack_propagate(False)
        tk.Label(top, text="SitGuard", fg=ui.ACCENT, bg=ui.BG,
                 font=ui.ui_font(15, "bold")).pack(side="left")
        tk.Label(top, text="  " + t("brand_sub"), fg=ui.TEXT_FAINT, bg=ui.BG,
                 font=ui.ui_font(9)).pack(side="left", pady=(ui.dp(6), 0))
        self.btn_settings = ui.RoundButton(top, t("settings"),
                                          command=self.app.open_settings,
                                          width=58, height=28, radius=9, fill=ui.BG_3,
                                          font=ui.ui_font(8), bg=ui.BG)
        self.btn_settings.pack(side="right")

        mid = tk.Frame(parent, bg=ui.BG)
        mid.pack(fill="x", padx=ui.dp(18), pady=(ui.dp(2), 0))
        self.ring = RingMeter(mid, size=ui.dp(200), bg=ui.BG)
        self.ring.pack(side="left")
        right = tk.Frame(mid, bg=ui.BG)
        right.pack(side="left", fill="both", expand=True, padx=(ui.dp(12), 0),
                   pady=ui.dp(8))
        self.preview = PreviewPanel(right, width=166, height=94)
        self.preview.pack(fill="x")
        self.lbl_presence = tk.Label(right, text=t("init"), fg=ui.TEXT_DIM, bg=ui.BG,
                                     font=self._fonts["small"], anchor="w",
                                     justify="left")
        self.lbl_presence.pack(fill="x", pady=(ui.dp(9), 0))
        self.lbl_presence_detail = tk.Label(right, text="", fg=ui.TEXT_FAINT, bg=ui.BG,
                                           font=self._fonts["tiny"], anchor="w",
                                           justify="left", wraplength=ui.dp(150))
        self.lbl_presence_detail.pack(fill="x", pady=(ui.dp(2), 0))
        self.btn_stand = ui.RoundButton(right, t("stand_mode"),
                                        command=self.app.toggle_standing,
                                        width=78, height=24, radius=8, fill=ui.BG_2,
                                        font=ui.ui_font(8), bg=ui.BG)
        self.btn_stand.pack(side="left", pady=(ui.dp(9), 0))
        self.btn_camera = ui.RoundButton(right, t("camera_off_btn"),
                                         command=self.app.toggle_camera,
                                         width=78, height=24, radius=8, fill=ui.BG_2,
                                         font=ui.ui_font(8), bg=ui.BG)
        self.btn_camera.pack(side="left", padx=(ui.dp(6), 0), pady=(ui.dp(9), 0))

        self.lbl_heading = tk.Label(parent, text=t("recognizing"), fg=ui.TEXT, bg=ui.BG,
                                    font=ui.ui_font(15, "bold"))
        self.lbl_heading.pack(fill="x", padx=ui.dp(18), pady=(ui.dp(6), 0))
        self.lbl_sub = tk.Label(parent, text="", fg=ui.TEXT_DIM, bg=ui.BG,
                                font=self._fonts["small"], wraplength=ui.dp(384),
                                justify="left")
        self.lbl_sub.pack(fill="x", padx=ui.dp(18), pady=(ui.dp(3), 0))

        card = tk.Frame(parent, bg=ui.BG_2, highlightthickness=1,
                        highlightbackground=ui.BORDER)
        card.pack(fill="x", padx=ui.dp(18), pady=(ui.dp(10), 0))
        inner = tk.Frame(card, bg=ui.BG_2)
        inner.pack(fill="x", padx=ui.dp(14), pady=ui.dp(8))
        self.stat_vars = {}
        for key, title in (("sit", t("stat_sit")), ("breaks", t("stat_breaks")),
                           ("rem", t("stat_reminders"))):
            col = tk.Frame(inner, bg=ui.BG_2)
            col.pack(side="left", expand=True, fill="x")
            var = tk.StringVar(value="—")
            self.stat_vars[key] = var
            tk.Label(col, textvariable=var, fg=ui.TEXT, bg=ui.BG_2,
                     font=self._fonts["num"]).pack(anchor="w")
            tk.Label(col, text=title, fg=ui.TEXT_FAINT, bg=ui.BG_2,
                     font=self._fonts["tiny"]).pack(anchor="w")

        actions = tk.Frame(parent, bg=ui.BG)
        actions.pack(fill="x", padx=ui.dp(18), pady=(ui.dp(12), 0))
        self.btn_pause = ui.RoundButton(actions, t("pause"),
                                        command=self.app.toggle_pause, width=118, height=38)
        self.btn_pause.pack(side="left")
        self.btn_test = ui.RoundButton(actions, t("test_reminder"),
                                       command=self.app.test_break, width=112, height=38,
                                       icon="🔔")
        self.btn_test.pack(side="left", padx=(ui.dp(10), 0))
        self.btn_min = ui.RoundButton(actions, t("to_tray"), command=self.app.hide_window,
                                      width=118, height=38, icon="▾", fill=ui.BG_3)
        self.btn_min.pack(side="right")

        self.lbl_footer = tk.Label(parent, text=t("footer"), fg=ui.TEXT_FAINT, bg=ui.BG,
                                   font=ui.ui_font(7))
        self.lbl_footer.pack(side="bottom", pady=(0, ui.dp(8)))

    # ---- 迷你计时器 ----
    def _draw_mini(self) -> None:
        c = self.mini
        c.delete("all")
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 24 or h < 24:
            return
        snap = self._last_snap
        time_text, label, color, ratio = self._mini_values(snap)
        d = min(w, h) - max(8, int(min(w, h) * 0.08))
        x1 = (w - d) / 2
        y1 = (h - d) / 2
        box = (x1, y1, x1 + d, y1 + d)
        th = max(4, int(d * 0.055))
        pad = th / 2
        ring_box = (box[0] + pad, box[1] + pad, box[2] - pad, box[3] - pad)
        c.create_oval(*ring_box, outline="#2a303a", width=th)
        if ratio > 0.002:
            c.create_line(*arc_points(ring_box, 90, -360 * ratio), fill=color,
                          width=th, capstyle=tk.ROUND, joinstyle=tk.ROUND, smooth=True)
        time_px = max(12, int(d * 0.26))
        c.create_text(w / 2, h / 2 - d * 0.035, text=time_text, fill=ui.TEXT,
                      font=ui.pixel_font(time_px, "bold"), anchor="center")
        if d > 110:
            c.create_text(w / 2, h / 2 + d * 0.19, text=label, fill=ui.TEXT_DIM,
                          font=ui.pixel_font(max(8, int(d * 0.06))), anchor="center")
        icon_px = max(10, int(d * 0.075))
        c.create_text(w - 8, 7, text="⚙", anchor="ne", fill=ui.TEXT_FAINT,
                      font=ui.pixel_font(icon_px), tags="gear")
        c.create_text(w - 8, h - 7, text="⤢", anchor="se", fill=ui.TEXT_FAINT,
                      font=ui.pixel_font(icon_px), tags="restore")
        c.tag_bind("gear", "<Button-1>", lambda _e: self.app.open_settings())
        c.tag_bind("restore", "<Button-1>", lambda _e: self.restore_size())

    def _mini_values(self, snap: Snapshot | None) -> tuple[str, str, str, float]:
        if snap is None:
            return "--:--", t("until_reminder"), ui.TEXT_FAINT, 0.0
        if snap.phase is Phase.PAUSED:
            return t("paused_ring"), "", "#3a404c", 1.0
        if snap.phase is Phase.BREAK:
            total = max(1.0, snap.break_total)
            return (ui.fmt_clock(snap.break_remaining), t("break_countdown"),
                    ui.WARN, max(0.001, min(1.0, snap.break_remaining / total)))
        sit = snap.sitting_seconds
        limit = max(1.0, snap.sit_limit)
        ratio = max(0.001, min(1.0, sit / limit))
        if snap.posture == "standing":
            return ui.fmt_clock(max(0.0, limit - sit)), t("standing_heading"), ui.GOOD, ratio
        if not snap.present:
            return ui.fmt_clock(max(0.0, limit - sit)), t("away_heading"), "#5b6474", ratio
        color = ui.DANGER if ratio >= 1.0 else (ui.WARN if ratio >= 0.8 else ui.ACCENT)
        return ui.fmt_clock(max(0.0, limit - sit)), t("until_reminder"), color, ratio

    # ---- 刷新 ----
    def refresh(self, snap: Snapshot, camera_state: str) -> None:
        self._last_snap = snap
        self._last_camera_state = camera_state
        if self._mode == "mini":
            self._draw_mini()
        elif self._mode == "full":
            self._refresh_full(snap, camera_state)

    def _refresh_full(self, snap: Snapshot, camera_state: str) -> None:
        phase = snap.phase
        sit = snap.sitting_seconds
        limit = snap.sit_limit
        ratio = sit / limit if limit else 0
        standing = snap.posture == "standing"

        if phase is Phase.PAUSED:
            heading = t("paused_heading")
            sub = t("paused_sub")
            self.ring.update_meter(ratio=1.0, time_text=t("paused_ring"),
                                   label=t("paused_heading"), sub="",
                                   color="#3a404c", dim=True)
            self.btn_pause.configure_text(t("resume"), "▶")
        elif phase is Phase.BREAK:
            heading = t("break_heading")
            sub = t("break_sub")
            self.ring.update_meter(ratio=1.0, time_text=ui.fmt_clock(snap.break_remaining),
                                   label=t("break_countdown"), sub=t("get_up"),
                                   color=ui.WARN)
            self.btn_pause.configure_text(t("pause"))
        else:
            if standing:
                heading = t("standing_heading")
                reset_after = float(getattr(self.app.config, "standing_reset_seconds", 180))
                left = max(0, int(reset_after - snap.standing_seconds))
                if sit > 0 and left > 0:
                    sub = t("standing_sub_reset", n=int(snap.standing_seconds), m=left)
                else:
                    sub = t("standing_sub", n=int(snap.standing_seconds))
                self.ring.update_meter(ratio=0.001, time_text=ui.fmt_clock(sit),
                                       label=t("sit_elapsed"),
                                       sub=t("standing_seconds",
                                             n=int(snap.standing_seconds)),
                                       color=ui.GOOD)
            else:
                if ratio >= 1.0:
                    heading = t("due_heading")
                    sub = t("due_sub")
                elif ratio >= 0.8:
                    heading = t("near_heading")
                    sub = t("near_sub")
                else:
                    heading = t("focus_heading")
                    sub = t("focus_sub")
                color = (ui.DANGER if ratio >= 1.0
                         else (ui.WARN if ratio >= 0.8 else ui.ACCENT))
                if not snap.present and camera_state == "ok":
                    heading = t("away_heading")
                    sub = t("away_sub")
                    color = "#5b6474"
                self.ring.update_meter(ratio=ratio,
                                       time_text=ui.fmt_clock(snap.sit_limit - sit),
                                       label=t("until_reminder"),
                                       sub=t("sat_for", t=ui.fmt_clock(sit)),
                                       color=color)
            self.btn_pause.configure_text(t("pause"))

        self.lbl_heading.configure(text=heading)
        self.lbl_sub.configure(text=sub)

        if camera_state == "ok":
            if standing:
                self.lbl_presence.configure(
                    text=t("present_standing", n=int(snap.standing_seconds)), fg=ui.GOOD)
            elif snap.posture == "sitting":
                self.lbl_presence.configure(text=t("present_sitting"), fg=ui.GOOD)
            elif snap.present:
                self.lbl_presence.configure(text=t("present_unknown"), fg=ui.GOOD)
            else:
                away = snap.away_seconds
                if away >= 60:
                    self.lbl_presence.configure(
                        text=t("away_minutes", m=int(away // 60)), fg=ui.WARN)
                else:
                    self.lbl_presence.configure(text=t("no_person"), fg=ui.WARN)
            detail = t("pose_ok") if snap.pose_ok else t("pose_face_only")
            if snap.pose_ok and not getattr(self.app.config, "calibration", None):
                detail = t("pose_cal_hint")
            self.lbl_presence_detail.configure(text=detail)
        elif camera_state == "error":
            self.lbl_presence.configure(text=t("cam_error"), fg=ui.DANGER)
            self.lbl_presence_detail.configure(text=t("cam_error_hint"))
        elif camera_state == "off":
            self.lbl_presence.configure(text=t("cam_off"), fg=ui.TEXT_FAINT)
            self.lbl_presence_detail.configure(text="")
        else:
            self.lbl_presence.configure(text=t("cam_starting"), fg=ui.TEXT_DIM)
            self.lbl_presence_detail.configure(text="")

        manual = self.app.manual_posture
        if manual == "standing":
            self.btn_stand.configure_text(t("sit_down"))
        elif manual == "sitting":
            self.btn_stand.configure_text(t("stand"))
        else:
            self.btn_stand.configure_text(t("stand_mode"))

        stats = snap.stats
        self.stat_vars["sit"].set(ui.fmt_sit_total(stats.sitting_seconds))
        self.stat_vars["breaks"].set(t("times", n=stats.breaks))
        self.stat_vars["rem"].set(t("times", n=stats.reminders))

    def update_preview(self, snap: CameraSnapshot, present: bool) -> None:
        if self._mode == "full" and self.app.config.show_preview:
            self.preview.update_frame(snap, present)

    def show_toast(self, text: str, color: str = ui.ACCENT, ms: int = 2600) -> None:
        if self._toast_after:
            self.root.after_cancel(self._toast_after)
        self.toast.configure(text=text, bg=color)
        self.toast.place(relx=0.5, y=ui.dp(10), anchor="n")
        self.toast.lift()
        self._toast_after = self.root.after(ms, self._hide_toast)

    def _hide_toast(self) -> None:
        self._toast_after = None
        self.toast.place_forget()

    def set_camera_button(self, enabled: bool) -> None:
        if hasattr(self, "btn_camera"):
            self.btn_camera.configure_text(
                t("camera_off_btn") if enabled else t("camera_on_btn"))


# ---------------------------------------------------------------------------
# 休息提醒（全屏遮罩）
# ---------------------------------------------------------------------------


class BreakOverlay:
    def __init__(self, app, root: tk.Tk):
        self.app = app
        self.root = root
        self.win: tk.Toplevel | None = None
        self._pulse_job = None
        self._pulse = 0

    def show(self, total_seconds: float, reason: str) -> None:
        if self.win is not None:
            return
        win = tk.Toplevel(self.root)
        self.win = win
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.94)
        win.configure(bg="#0a0c10")
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        win.geometry(f"{sw}x{sh}+0+0")
        self._build(win)
        win.update_idletasks()
        try:
            win.grab_set()
        except tk.TclError:
            pass
        try:
            import ctypes

            hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
            ctypes.windll.user32.SetForegroundWindow(hwnd or win.winfo_id())
        except Exception:  # noqa: BLE001
            pass
        win.focus_force()
        win.bind("<Escape>", lambda _e: None)
        self._pulse_loop()

    def _build(self, win: tk.Toplevel) -> None:
        card_w, card_h = ui.dp(760), ui.dp(420)
        card = tk.Frame(win, bg=ui.BG_2, highlightthickness=1,
                        highlightbackground="#3a4150")
        card.place(relx=0.5, rely=0.5, anchor="center", width=card_w, height=card_h)

        left = tk.Frame(card, bg=ui.BG_2)
        left.place(x=ui.dp(34), y=ui.dp(24), width=ui.dp(438), height=card_h - ui.dp(40))
        right = tk.Frame(card, bg=ui.BG_2)
        right.place(x=ui.dp(492), y=ui.dp(30), width=ui.dp(240), height=card_h - ui.dp(52))

        tk.Label(left, text=t("overlay_brand"), fg=ui.ACCENT_DEEP, bg=ui.BG_2,
                 font=ui.ui_font(9, "bold"), anchor="w").pack(fill="x")
        self.lbl_title = tk.Label(left, text=t("overlay_title"), fg=ui.TEXT, bg=ui.BG_2,
                                  font=ui.ui_font(24, "bold"), anchor="w")
        self.lbl_title.pack(fill="x", pady=(ui.dp(8), 0))
        self.lbl_reason = tk.Label(left, text="", fg=ui.TEXT_DIM, bg=ui.BG_2,
                                   font=ui.ui_font(10), anchor="w", justify="left",
                                   wraplength=ui.dp(430))
        self.lbl_reason.pack(fill="x", pady=(ui.dp(5), 0))

        ring_size = ui.dp(150)
        ring = tk.Canvas(left, width=ring_size, height=ring_size, bg=ui.BG_2,
                         highlightthickness=0)
        ring.pack(pady=(ui.dp(10), 0))
        self._ring = ring
        pad = ui.dp(10)
        box = (pad, pad, ring_size - pad, ring_size - pad)
        self._ring_bg = ring.create_oval(*box, outline="#2c323d", width=ui.dp(11))
        self._ring_box = box
        self._ring_arc = ring.create_line(
            *arc_points(box, 90, -1.5), fill=ui.WARN, width=ui.dp(11),
            capstyle=tk.ROUND, joinstyle=tk.ROUND, smooth=True)
        self._ring_text = ring.create_text(ring_size / 2, ring_size / 2, text="5:00",
                                           fill=ui.TEXT, font=ui.mono_font(27, "bold"))

        self.lbl_status = tk.Label(left, text=t("overlay_idle"),
                                   fg=ui.TEXT_DIM, bg=ui.BG_2, font=ui.ui_font(10),
                                   wraplength=ui.dp(430), justify="left", anchor="w")
        self.lbl_status.pack(fill="x", pady=(ui.dp(8), 0))

        row = tk.Frame(left, bg=ui.BG_2)
        row.pack(pady=(ui.dp(13), 0), anchor="w")
        self.btn_stand = ui.RoundButton(row, t("btn_stood"), command=self.app.confirm_break,
                                        width=150, height=42, radius=12, accent=True,
                                        bg=ui.BG_2, font=ui.ui_font(10, "bold"))
        self.btn_stand.pack(side="left")
        self.btn_snooze = ui.RoundButton(row, t("btn_snooze"), command=self.app.snooze_break,
                                         width=180, height=42, radius=12, fill=ui.BG_3,
                                         bg=ui.BG_2, font=ui.ui_font(9))
        self.btn_snooze.pack(side="left", padx=(ui.dp(12), 0))

        self.btn_close = tk.Label(left, text=t("btn_close_break"), fg=ui.TEXT_FAINT, bg=ui.BG_2,
                                  font=ui.ui_font(8), cursor="hand2")
        self.btn_close.pack(anchor="w", pady=(ui.dp(10), 0))
        self.btn_close.bind("<Button-1>", lambda _e: self.app.confirm_break())
        self.btn_close.bind("<Enter>", lambda _e: self.btn_close.configure(fg=ui.ACCENT))
        self.btn_close.bind("<Leave>", lambda _e: self.btn_close.configure(fg=ui.TEXT_FAINT))

        # 右侧摄像头
        cam_card = tk.Frame(right, bg="#15181f", highlightthickness=1,
                            highlightbackground=ui.BORDER)
        cam_card.pack(fill="x")
        tk.Label(cam_card, text=t("cam_pose"), fg=ui.TEXT_FAINT, bg="#15181f",
                 font=ui.ui_font(8), anchor="w").pack(fill="x", padx=ui.dp(10),
                                                      pady=(ui.dp(8), ui.dp(4)))
        self.preview = PreviewPanel(cam_card, width=214, height=120)
        self.preview.pack(padx=ui.dp(10), pady=(0, ui.dp(6)))
        self.lbl_monitor = tk.Label(cam_card, text="", fg=ui.TEXT_DIM, bg="#15181f",
                                    font=ui.ui_font(8), anchor="w", justify="left",
                                    wraplength=ui.dp(210))
        self.lbl_monitor.pack(fill="x", padx=ui.dp(10), pady=(0, ui.dp(8)))
        self.lbl_foot = tk.Label(right, text=t("overlay_foot"),
                                 fg=ui.TEXT_FAINT, bg=ui.BG_2, font=ui.ui_font(8),
                                 justify="left", anchor="w")
        self.lbl_foot.pack(fill="x", pady=(ui.dp(12), 0))

    def _pulse_loop(self) -> None:
        if not self.win:
            return
        self._pulse = (self._pulse + 1) % 2
        try:
            self._ring.itemconfigure(self._ring_arc,
                                     fill=ui.WARN if self._pulse else "#d98c3a")
        except tk.TclError:
            return
        self._pulse_job = self.win.after(900, self._pulse_loop)

    def update(self, snap: Snapshot, camera_snap: CameraSnapshot) -> None:
        if not self.win:
            return
        remaining = snap.break_remaining
        total = max(1.0, snap.break_total)
        ratio = max(0.001, min(1.0, remaining / total))
        self._ring.itemconfigure(self._ring_text, text=ui.fmt_clock(remaining))
        self._ring.coords(self._ring_arc, *arc_points(self._ring_box, 90, -360 * ratio))
        self.lbl_reason.configure(
            text=t("overlay_reason", d=fmt_duration(snap.sitting_seconds))
        )
        if snap.posture == "standing":
            stood = int(snap.standing_seconds)
            if snap.standing_seconds >= snap.stand_target:
                self.lbl_status.configure(text=t("standing_almost"), fg=ui.GOOD)
            else:
                need = max(1, int(snap.stand_target - snap.standing_seconds))
                self.lbl_status.configure(
                    text=t("standing_need", s=stood, n=need), fg=ui.GOOD)
        elif not camera_snap.seen and snap.gone_seconds >= 2:
            left = max(0, int(float(getattr(self.app.config, "break_absent_seconds", 12))
                              - snap.gone_seconds))
            self.lbl_status.configure(
                text=t("gone_left", n=left), fg=ui.GOOD)
        elif not snap.pose_ok:
            self.lbl_status.configure(
                text=t("pose_off_tip"), fg=ui.WARN)
        else:
            self.lbl_status.configure(
                text=t("overlay_tip"),
                fg=ui.TEXT_DIM)
        self.preview.update_frame(camera_snap, snap.present)
        if snap.posture == "standing":
            self.lbl_monitor.configure(text=t("overlay_mon_standing"), fg=ui.GOOD)
        elif not camera_snap.seen and snap.gone_seconds >= 2:
            self.lbl_monitor.configure(text=t("overlay_mon_gone"), fg=ui.GOOD)
        elif snap.present:
            self.lbl_monitor.configure(text=t("overlay_mon_sitting"), fg=ui.WARN)
        else:
            self.lbl_monitor.configure(text=t("overlay_mon_away"), fg=ui.GOOD)

    def close(self) -> None:
        if self._pulse_job:
            try:
                self.win.after_cancel(self._pulse_job)
            except Exception:  # noqa: BLE001
                pass
            self._pulse_job = None
        if self.win:
            try:
                self.win.grab_release()
                self.win.destroy()
            except tk.TclError:
                pass
            self.win = None


# ---------------------------------------------------------------------------
# 设置
# ---------------------------------------------------------------------------


class SettingsWindow:
    def __init__(self, app, root: tk.Tk):
        self.app = app
        self.root = root
        self.win: tk.Toplevel | None = None

    def open(self) -> None:
        if self.win is not None:
            self.win.lift()
            self.win.focus_force()
            return
        cfg = self.app.config
        win = tk.Toplevel(self.root)
        self.win = win
        win.title(t("settings_title"))
        win.configure(bg=ui.BG)
        win.resizable(False, False)
        win.transient(self.root)
        ui.center_window(win, ui.dp(440), ui.dp(748), anchor="center")
        win.protocol("WM_DELETE_WINDOW", self.close)

        body = tk.Frame(win, bg=ui.BG)
        body.pack(fill="both", expand=True, padx=ui.dp(22), pady=ui.dp(12))

        tk.Label(body, text=t("settings_heading"), fg=ui.TEXT, bg=ui.BG,
                 font=ui.ui_font(16, "bold")).pack(anchor="w")
        tk.Label(body, text=t("settings_sub"), fg=ui.TEXT_FAINT, bg=ui.BG,
                 font=ui.ui_font(8)).pack(anchor="w", pady=(ui.dp(2), ui.dp(8)))

        self.vars: dict[str, tk.Variable] = {}
        self._row(body, "row_sit", tk.IntVar(value=cfg.sit_minutes), "minutes",
                  from_=5, to=240, step=5, hint_key="hint_sit")
        self._row(body, "row_break", tk.IntVar(value=cfg.break_minutes), "minutes",
                  from_=1, to=30, step=1, hint_key="hint_break")
        self._row(body, "row_away", tk.IntVar(value=cfg.away_minutes), "minutes",
                  from_=1, to=60, step=1, hint_key="hint_away")
        self._row(body, "row_stand_break",
                  tk.IntVar(value=int(cfg.standing_break_seconds)), "seconds",
                  from_=3, to=120, step=1, hint_key="hint_stand_break")
        self._row(body, "row_break_absent",
                  tk.IntVar(value=int(cfg.break_absent_seconds)), "seconds",
                  from_=5, to=120, step=1, hint_key="hint_break_absent")
        self._row(body, "row_stand_reset",
                  tk.IntVar(value=int(cfg.standing_reset_seconds)), "seconds",
                  from_=30, to=900, step=30, hint_key="hint_stand_reset")
        self._row(body, "row_cam", tk.IntVar(value=cfg.camera_index), "",
                  from_=0, to=8, step=1, hint_key="hint_cam")
        self._row(body, "row_sens", tk.DoubleVar(value=cfg.sensitivity), "",
                  from_=0.3, to=0.9, step=0.05, decimals=2, hint_key="hint_sens")

        self._check(body, "chk_pose", "posture_enabled")
        self._check(body, "chk_sound", "sound")
        self._check(body, "chk_autostart", "autostart")
        self._check(body, "chk_preview", "show_preview")
        self._check(body, "chk_tray", "minimize_to_tray")
        self._check(body, "chk_top", "always_on_top")

        lang_row = tk.Frame(body, bg=ui.BG)
        lang_row.pack(fill="x", pady=(ui.dp(6), 0))
        tk.Label(lang_row, text=t("row_lang"), fg=ui.TEXT, bg=ui.BG,
                 font=ui.ui_font(9)).pack(side="left")
        for code, name in (("zh", "中文"), ("en", "English")):
            active = getattr(cfg, "language", "zh") == code
            ui.RoundButton(
                lang_row, name, command=lambda c=code: self.app.set_language(c),
                width=66, height=26, radius=8,
                fill=ui.ACCENT if active else ui.BG_3,
                font=ui.ui_font(9), bg=ui.BG,
            ).pack(side="left", padx=(ui.dp(8), 0))

        cal_row = tk.Frame(body, bg=ui.BG)
        cal_row.pack(fill="x", pady=(ui.dp(8), 0))
        ui.RoundButton(cal_row, t("cal_btn"), command=self.app.open_calibration,
                       width=132, height=30, radius=9, fill=ui.BG_3,
                       font=ui.ui_font(9)).pack(side="left")
        tk.Label(cal_row, text=t("cal_hint"), fg=ui.TEXT_FAINT, bg=ui.BG,
                 font=ui.ui_font(8), wraplength=ui.dp(250), justify="left").pack(
                     side="left", padx=ui.dp(8))

        row = tk.Frame(body, bg=ui.BG)
        row.pack(fill="x", side="bottom", pady=(ui.dp(10), 0))
        ui.RoundButton(row, t("save"), command=self.save, width=120, height=38,
                       accent=True, font=ui.ui_font(10, "bold")).pack(side="right")
        ui.RoundButton(row, t("cancel"), command=self.close, width=90, height=38,
                       bg=ui.BG_3).pack(side="right", padx=(0, ui.dp(10)))

        self._sync_vars()

    def _row(self, parent, key: str, var, unit_key: str, from_: float, to: float,
             step: float, hint_key: str = "", decimals: int = 0) -> None:
        wrap = tk.Frame(parent, bg=ui.BG)
        wrap.pack(fill="x", pady=(0, ui.dp(7)))
        head = tk.Frame(wrap, bg=ui.BG)
        head.pack(fill="x")
        tk.Label(head, text=t(key), fg=ui.TEXT, bg=ui.BG,
                 font=ui.ui_font(9)).pack(side="left")
        kwargs = {}
        if decimals:
            kwargs["format"] = f"%.{decimals}f"
        spin = tk.Spinbox(
            head, from_=from_, to=to, increment=step, width=5, justify="right",
            textvariable=var, bg=ui.BG_3, fg=ui.TEXT, buttonbackground=ui.BG_3,
            insertbackground=ui.TEXT, relief="flat", font=ui.ui_font(9),
            highlightthickness=0, **kwargs,
        )
        spin.pack(side="right")
        if unit_key:
            tk.Label(head, text=t(unit_key), fg=ui.TEXT_FAINT, bg=ui.BG,
                     font=ui.ui_font(8)).pack(side="right", padx=(0, ui.dp(6)))
        if hint_key:
            tk.Label(wrap, text=t(hint_key), fg=ui.TEXT_FAINT, bg=ui.BG,
                     font=ui.ui_font(8)).pack(anchor="w", pady=(ui.dp(1), 0))
        self.vars[key] = var

    def _check(self, parent, key: str, config_key: str) -> None:
        var = tk.BooleanVar(value=False)
        self.vars[config_key] = var
        row = tk.Frame(parent, bg=ui.BG)
        row.pack(fill="x", pady=ui.dp(1))
        cb = tk.Checkbutton(row, text=t(key), variable=var, bg=ui.BG, fg=ui.TEXT,
                            selectcolor="#2f3542", activebackground=ui.BG,
                            activeforeground=ui.ACCENT, font=ui.ui_font(9),
                            highlightthickness=0, bd=0, anchor="w",
                            indicatoron=True, relief="flat", padx=ui.dp(2), pady=ui.dp(1))
        cb.pack(anchor="w")

    def _sync_vars(self) -> None:
        cfg = self.app.config
        self.vars["posture_enabled"].set(cfg.posture_enabled)
        self.vars["sound"].set(cfg.sound)
        self.vars["autostart"].set(cfg.autostart)
        self.vars["show_preview"].set(cfg.show_preview)
        self.vars["minimize_to_tray"].set(cfg.minimize_to_tray)
        self.vars["always_on_top"].set(cfg.always_on_top)

    def save(self) -> None:
        cfg = self.app.config
        try:
            cfg.sit_minutes = int(float(self.vars["row_sit"].get()))
            cfg.break_minutes = int(float(self.vars["row_break"].get()))
            cfg.away_minutes = int(float(self.vars["row_away"].get()))
            cfg.break_absent_seconds = float(self.vars["row_break_absent"].get())
            cfg.standing_break_seconds = float(self.vars["row_stand_break"].get())
            cfg.standing_reset_seconds = float(self.vars["row_stand_reset"].get())
            cfg.camera_index = int(float(self.vars["row_cam"].get()))
            cfg.sensitivity = round(float(self.vars["row_sens"].get()), 2)
        except (ValueError, tk.TclError):
            self.app.notify(t("invalid_number"), ui.DANGER)
            return
        cfg.posture_enabled = bool(self.vars["posture_enabled"].get())
        cfg.sound = bool(self.vars["sound"].get())
        cfg.autostart = bool(self.vars["autostart"].get())
        cfg.show_preview = bool(self.vars["show_preview"].get())
        cfg.minimize_to_tray = bool(self.vars["minimize_to_tray"].get())
        cfg.always_on_top = bool(self.vars["always_on_top"].get())
        self.app.apply_settings()
        self.close()
        self.app.notify(t("settings_saved"), ui.GOOD)

    def close(self) -> None:
        if self.win:
            self.win.destroy()
            self.win = None

# ---------------------------------------------------------------------------
# 姿势校准（记录坐姿/站姿特征）
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 姿势校准（记录坐姿/站姿特征）
# ---------------------------------------------------------------------------


class CalibrationWindow:
    def __init__(self, app, root: tk.Tk):
        self.app = app
        self.root = root
        self.win: tk.Toplevel | None = None
        self._poll_job = None
        self._capture_job = None
        self._samples: list[PostureProfile] = []
        self._capture_which: str | None = None
        self._capture_until = 0.0
        self._sitting: PostureProfile | None = None
        self._standing: PostureProfile | None = None

    def show(self) -> None:
        if self.win is not None:
            self.win.lift()
            self.win.focus_force()
            return
        win = tk.Toplevel(self.root)
        self.win = win
        win.title(t("cal_title"))
        win.configure(bg=ui.BG)
        win.resizable(False, False)
        win.transient(self.root)
        win.attributes("-topmost", True)
        ui.center_window(win, ui.dp(560), ui.dp(470), anchor="center")
        win.protocol("WM_DELETE_WINDOW", self.close)

        tk.Label(win, text=t("cal_heading"), fg=ui.TEXT, bg=ui.BG,
                 font=ui.ui_font(16, "bold")).pack(anchor="w", padx=ui.dp(22),
                                                   pady=(ui.dp(16), 0))
        tk.Label(win, text=t("cal_desc"),
                 fg=ui.TEXT_DIM, bg=ui.BG, font=ui.ui_font(9), justify="left",
                 wraplength=ui.dp(510)).pack(anchor="w", padx=ui.dp(22),
                                             pady=(ui.dp(4), ui.dp(10)))

        self.preview = PreviewPanel(win, width=250, height=140)
        self.preview.pack(anchor="w", padx=ui.dp(22))

        row = tk.Frame(win, bg=ui.BG)
        row.pack(fill="x", padx=ui.dp(22), pady=(ui.dp(12), 0))
        ui.RoundButton(row, t("cal_sit_btn"), command=lambda: self._capture("sitting"),
                       width=132, height=36, fill=ui.BG_3,
                       font=ui.ui_font(9)).pack(side="left")
        ui.RoundButton(row, t("cal_stand_btn"), command=lambda: self._capture("standing"),
                       width=132, height=36, fill=ui.BG_3,
                       font=ui.ui_font(9)).pack(side="left", padx=(ui.dp(10), 0))

        self.lbl_sit = tk.Label(win, text=t("cal_sit_none"), fg=ui.TEXT_DIM, bg=ui.BG,
                                font=ui.ui_font(9), anchor="w")
        self.lbl_sit.pack(fill="x", padx=ui.dp(22), pady=(ui.dp(10), 0))
        self.lbl_stand = tk.Label(win, text=t("cal_stand_none"), fg=ui.TEXT_DIM, bg=ui.BG,
                                  font=ui.ui_font(9), anchor="w")
        self.lbl_stand.pack(fill="x", padx=ui.dp(22), pady=(ui.dp(2), 0))
        self.lbl_tip = tk.Label(win, text="", fg=ui.TEXT_FAINT, bg=ui.BG,
                                font=ui.ui_font(8), anchor="w", justify="left",
                                wraplength=ui.dp(510))
        self.lbl_tip.pack(fill="x", padx=ui.dp(22), pady=(ui.dp(4), 0))

        bottom = tk.Frame(win, bg=ui.BG)
        bottom.pack(fill="x", side="bottom", padx=ui.dp(22), pady=ui.dp(16))
        ui.RoundButton(bottom, t("cal_save"), command=self._save, width=132, height=38,
                       accent=True, font=ui.ui_font(10, "bold")).pack(side="right")
        ui.RoundButton(bottom, t("cancel"), command=self.close, width=88, height=38,
                       bg=ui.BG_3).pack(side="right", padx=(0, ui.dp(10)))
        win.lift()
        win.focus_force()
        self._load_existing()
        self._poll_preview()

    def _load_existing(self) -> None:
        raw = getattr(self.app.config, "calibration", None) or {}
        self._sitting = PostureProfile.from_dict(raw.get("sitting")) if raw else None
        self._standing = PostureProfile.from_dict(raw.get("standing")) if raw else None
        self._update_labels()

    def _poll_preview(self) -> None:
        if not self.win:
            return
        snap = self.app._camera_snapshot
        if snap is not None:
            self.preview.update_frame(snap, snap.seen)
        self._poll_job = self.win.after(200, self._poll_preview)

    def _capture(self, which: str) -> None:
        if self._capture_job:
            return
        self._capture_which = which
        self._samples = []
        self._capture_until = time.monotonic() + 1.6
        self.lbl_tip.configure(text=t("cal_sampling"))
        self._sample_tick()

    def _sample_tick(self) -> None:
        if not self.win:
            return
        snap = self.app._camera_snapshot
        if snap is not None and snap.profile is not None:
            self._samples.append(snap.profile)
        if time.monotonic() < self._capture_until:
            self._capture_job = self.win.after(100, self._sample_tick)
            return
        self._capture_job = None
        if not self._samples:
            self.lbl_tip.configure(text=t("cal_no_frame"))
            return
        profile = median_profile(self._samples)
        if self._capture_which == "sitting":
            self._sitting = profile
        else:
            self._standing = profile
        self._capture_which = None
        self._update_labels()

    def _describe(self, profile: PostureProfile | None) -> str:
        if profile is None:
            return t("cal_sit_none").split("：")[-1] if False else "—"
        if not profile.visible:
            return t("cal_desc_noface")
        if profile.face_y is not None and profile.shoulder_y is not None:
            return t("cal_desc_visible", f=int(profile.face_y * 100),
                     s=int(profile.shoulder_y * 100))
        if profile.face_y is not None:
            return t("cal_desc_face", f=int(profile.face_y * 100))
        return t("cal_unrecorded")

    def _update_labels(self) -> None:
        self.lbl_sit.configure(text=t("cal_sit_done", d=self._describe(self._sitting)),
                               fg=ui.GOOD if self._sitting else ui.TEXT_DIM)
        self.lbl_stand.configure(text=t("cal_stand_done", d=self._describe(self._standing)),
                                 fg=ui.GOOD if self._standing else ui.TEXT_DIM)
        if self._sitting and self._standing:
            if self._standing.visible:
                self.lbl_tip.configure(text=t("cal_done"))
            else:
                self.lbl_tip.configure(
                    text=t("cal_done_noface"))
        else:
            self.lbl_tip.configure(text=t("cal_need_both"))

    def _save(self) -> None:
        if not self._sitting or not self._standing:
            self.lbl_tip.configure(text=t("cal_need_both"))
            return
        self.app.set_calibration(self._sitting, self._standing)
        self.app.notify(t("cal_saved"), ui.GOOD)
        self.close()

    def close(self) -> None:
        if self._poll_job and self.win:
            try:
                self.win.after_cancel(self._poll_job)
            except Exception:  # noqa: BLE001
                pass
            self._poll_job = None
        if self._capture_job and self.win:
            try:
                self.win.after_cancel(self._capture_job)
            except Exception:  # noqa: BLE001
                pass
            self._capture_job = None
        if self.win:
            self.win.destroy()
            self.win = None

