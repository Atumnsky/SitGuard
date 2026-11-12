"""通用 UI 组件与主题（支持高 DPI 缩放）。

所有像素尺寸都通过 dp() 换算：dp(420) 在 200% 缩放下等于 840 物理像素，
窗口的“视觉大小”保持一致，但文字与线条是原生物理像素，不会发虚。
字体用磅值，由 Tk 的 scaling 按真实 DPI 放大。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont

# ---------- 配色 ----------
BG = "#12141a"
BG_2 = "#191c24"
BG_3 = "#22262f"
CARD = "#1b1f27"
BORDER = "#2b303b"
TEXT = "#eef1f6"
TEXT_DIM = "#9aa3b2"
TEXT_FAINT = "#646c7c"
ACCENT = "#4fd1c5"
ACCENT_DEEP = "#2c9d94"
WARN = "#f6ad55"
DANGER = "#fc8181"
GOOD = "#68d391"
BLUE = "#63b3ed"

FONT_FAMILY = "Microsoft YaHei UI"
FONT_FALLBACK = "Microsoft YaHei"
FONT_EMOJI = "Segoe UI Emoji"

SCALE = 1.0
DPI = 96.0


def configure_scale(dpi: float, root: tk.Misc | None = None) -> float:
    """按真实 DPI 设定缩放；返回缩放倍数。"""
    global SCALE, DPI
    DPI = max(72.0, float(dpi))
    SCALE = max(1.0, DPI / 96.0)
    if root is not None:
        try:
            root.tk.call("tk", "scaling", DPI / 72.0)
        except tk.TclError:
            pass
    return SCALE


def dp(value: float) -> int:
    """设计像素 → 物理像素。"""
    return int(round(value * SCALE))


_FONT_CACHE: dict[tuple, tkfont.Font] = {}


def ui_font(size: int, weight: str = "normal") -> tkfont.Font:
    key = ("ui", size, weight)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    font = None
    for family in (FONT_FAMILY, FONT_FALLBACK, "SimHei"):
        try:
            font = tkfont.Font(family=family, size=size, weight=weight)
            break
        except tk.TclError:
            continue
    if font is None:
        font = tkfont.Font(size=size, weight=weight)
    _FONT_CACHE[key] = font
    return font


def mono_font(size: int, weight: str = "bold") -> tkfont.Font:
    key = ("mono", size, weight)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    font = None
    for family in ("Consolas", "Cascadia Mono", "Courier New"):
        try:
            font = tkfont.Font(family=family, size=size, weight=weight)
            break
        except tk.TclError:
            continue
    if font is None:
        font = tkfont.Font(size=size, weight=weight)
    _FONT_CACHE[key] = font
    return font


def emoji_font(size: int = 11) -> tkfont.Font:
    try:
        return tkfont.Font(family=FONT_EMOJI, size=size)
    except tk.TclError:
        return ui_font(size)


def fmt_clock(seconds: float, always_hours: bool = False) -> str:
    seconds = max(0, int(round(seconds)))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h or always_hours:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def fmt_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h} 小时 {m} 分"
    if m:
        return f"{m} 分钟"
    return f"{s} 秒"


def fmt_sit_total(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m"
    if m:
        return f"{m}m"
    return f"{s}s"


def rounded_rect(canvas: tk.Canvas, x1, y1, x2, y2, r, **kwargs):
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    points = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, splinesteps=24, **kwargs)


def center_window(win: tk.Misc, width: int, height: int, anchor: str = "center",
                  margin: int = 24) -> None:
    """width/height 为物理像素；margin 为设计像素，内部自动换算。"""
    try:
        win.update_idletasks()
    except tk.TclError:
        return
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    margin = dp(margin)
    if anchor == "topright":
        x = sw - width - margin
        y = margin
    elif anchor == "bottomright":
        x = sw - width - margin
        y = sh - height - margin - dp(40)
    else:
        x = (sw - width) // 2
        y = (sh - height) // 2
    win.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")


class RoundButton(tk.Canvas):
    """圆角按钮，Canvas 绘制，带 hover / press / disabled 状态。"""

    def __init__(self, master, text: str, command=None, *, width: float = 120,
                 height: float = 38, radius: float = 12, fill: str = BG_3,
                 hover: str = "#2c313d", text_color: str = TEXT,
                 font: tkfont.Font | None = None, bg: str = BG,
                 accent: bool = False, icon: str = ""):
        w, h = dp(width), dp(height)
        super().__init__(master, width=w, height=h, bg=bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self._command = command
        self._btn_w, self._btn_h = w, h
        self._radius = dp(radius)
        self._fill, self._hover = fill, hover
        self._accent = accent
        self._text_color = text_color
        self._font = font or ui_font(9)
        self._text = text
        self._icon = icon
        self._enabled = True
        self._shape = None
        self._label = None
        self._draw()
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _bg_fill(self) -> str:
        if self._accent:
            return ACCENT if self._enabled else "#2a5552"
        return self._fill if self._enabled else "#1b1f27"

    def _fg_fill(self) -> str:
        if self._accent:
            return "#06211f"
        return self._text_color if self._enabled else TEXT_FAINT

    def _draw(self) -> None:
        self.delete("all")
        self._shape = rounded_rect(self, dp(1), dp(1), self._btn_w - dp(1),
                                   self._btn_h - dp(1), self._radius,
                                   fill=self._bg_fill(), outline="")
        label = f"{self._icon}  {self._text}" if self._icon else self._text
        self._label = self.create_text(self._btn_w / 2, self._btn_h / 2, text=label,
                                       fill=self._fg_fill(), font=self._font)

    def configure_text(self, text: str, icon: str | None = None) -> None:
        self._text = text
        if icon is not None:
            self._icon = icon
        self._draw()

    def set_enabled(self, enabled: bool) -> None:
        if self._enabled == enabled:
            return
        self._enabled = enabled
        self.configure(cursor="hand2" if enabled else "arrow")
        self._draw()

    def _on_enter(self, _e=None):
        if self._enabled and self._shape:
            self.itemconfigure(self._shape, fill="#63ddd2" if self._accent else self._hover)

    def _on_leave(self, _e=None):
        if self._enabled and self._shape:
            self.itemconfigure(self._shape, fill=self._bg_fill())

    def _on_press(self, _e=None):
        if self._enabled and self._shape:
            self.itemconfigure(self._shape, fill="#173f3b" if self._accent else "#313845")

    def _on_release(self, _e=None):
        if not self._enabled:
            return
        self._on_leave()
        if self._command:
            self._command()


class ProgressBar(tk.Canvas):
    def __init__(self, master, width: float = 300, height: float = 8, bg: str = BG_2,
                 color: str = ACCENT, **kwargs):
        w, h = dp(width), dp(height)
        super().__init__(master, width=w, height=h, bg=bg,
                         highlightthickness=0, bd=0, **kwargs)
        self._pb_w, self._pb_h = w, h
        self._color = color
        self._track = self.create_rectangle(0, 0, w, h, fill="#2a2f3a", outline="")
        self._bar = self.create_rectangle(0, 0, 0, h, fill=color, outline="")

    def set(self, ratio: float, color: str | None = None) -> None:
        ratio = max(0.0, min(1.0, ratio))
        self.coords(self._bar, 0, 0, max(0, self._pb_w * ratio), self._pb_h)
        if color:
            self.itemconfigure(self._bar, fill=color)
