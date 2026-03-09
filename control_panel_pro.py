"""
Premium control panel for WeChat group management — demo/marketing UI.

Usage:
  python control_panel_pro.py

Input:
  - Project root directory (auto-detected).
  - Signal files for agent communication in artifacts/.

Output:
  - Compact, minimal GUI that auto-starts the system on open.
  - Hides window when workflow runs; re-open via menu bar: 窗口 -> 显示主窗口.
  - HUD toasts (top-right) for key workflow events.
"""

from __future__ import annotations

import json
import os
import time
import queue
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, List, Optional

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Windows: Don't force DPI awareness — aggressive DPI modes can cause jagged
# lines and poor ClearType rendering. Let the OS handle scaling.

from modules.group_classifier import parse_classification
from modules.removal_precheck import build_removal_plan
from modules.suspicious_detector import extract_suspects
from modules.task_types import GroupThread, RemovalPlan, Suspect
from modules.unread_scanner import filter_unread_groups
from panel_state import PanelState, _serialize_state, load_state, save_state

# ─────────────────────────────  design system  ────────────────────────────────
# Platform-specific visual profiles.
# Windows: ttk-based layout using Win11 system colors.
# Mac: custom tk layout with SF Pro + navy palette.
IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

# Win11 / WeChat-companion palette
# Light: white window, white card, thin gray dividers, WeChat green accent
# Dark: near-black bg, slightly elevated surface, green accent dimmed
WIN_THEMES = {
    "light": {
        "bg":           "#ffffff",   # pure white window (WeChat sidebar bg)
        "surface":      "#f7f7f7",   # subtle off-white card
        "surface_alt":  "#ededed",   # hover / chip bg
        "divider":      "#f0f0f0",   # soft separator (avoids harsh 1px)
        "text":         "#191919",   # near-black primary text
        "text_secondary":"#888888",  # secondary / muted
        "accent":       "#07C160",   # WeChat green
        "accent_hover": "#06ad56",
        "accent_text":  "#ffffff",
        "border":       "#e0e0e0",
        "error":        "#d93025",
        "success":      "#07C160",
        "dot_idle":     "#07C160",
        "dot_pulse":    "#7debb5",
        "toast_bg":     "#323130",
    },
    "dark": {
        "bg":           "#1c1c1c",
        "surface":      "#2a2a2a",
        "surface_alt":  "#333333",
        "divider":      "#404040",   # softer dark separator
        "text":         "#f0f0f0",
        "text_secondary":"#909090",
        "accent":       "#07C160",
        "accent_hover": "#06ad56",
        "accent_text":  "#ffffff",
        "border":       "#3a3a3a",
        "error":        "#ff6b6b",
        "success":      "#07C160",
        "dot_idle":     "#07C160",
        "dot_pulse":    "#7debb5",
        "toast_bg":     "#323130",
    },
}

# Mac palette (navy/minimal — unchanged)
MAC_THEMES = {
    "light": {
        "bg":              "#fafbfc",
        "surface":         "#f1f4f8",
        "surface_elevated":"#ffffff",
        "primary":         "#1a365d",
        "primary_hover":   "#2c5282",
        "primary_contrast":"#ffffff",
        "text":            "#1a202c",
        "text_secondary":  "#718096",
        "border":          "#e2e8f0",
        "success":         "#276749",
        "error":           "#c53030",
        "toast_bg":        "#1a365d",
        "dot_idle":        "#1a365d",
        "dot_pulse":       "#2c5282",
    },
    "dark": {
        "bg":              "#0d1117",
        "surface":         "#161b22",
        "surface_elevated":"#21262d",
        "primary":         "#58a6ff",
        "primary_hover":   "#79b8ff",
        "primary_contrast":"#0d1117",
        "text":            "#e6edf3",
        "text_secondary":  "#8b949e",
        "border":          "#30363d",
        "success":         "#3fb950",
        "error":           "#f85149",
        "toast_bg":        "#21262d",
        "dot_idle":        "#58a6ff",
        "dot_pulse":       "#79b8ff",
    },
}

# Typography
WIN_FONTS  = {"xs": 9, "sm": 10, "base": 11, "lg": 12, "xl": 13, "2xl": 18, "3xl": 22}
MAC_FONTS  = {"xs": 9, "sm": 10, "base": 11, "lg": 12, "xl": 13, "2xl": 18, "3xl": 22}

# Spacing (px)
WIN_SPACE  = {"1": 4, "2": 8, "3": 10, "4": 16, "6": 20, "8": 28}
MAC_SPACE  = {"1": 4, "2": 8, "3": 12, "4": 16, "6": 24, "8": 32}


def _resolve_theme(state_theme: str) -> str:
    """Resolve 'system' to 'light' or 'dark' from OS preference."""
    if state_theme != "system":
        return state_theme
    if IS_WIN:
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                0, winreg.KEY_READ
            )
            val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return "dark" if val == 0 else "light"
        except Exception:
            pass
    return "light"


def _C_for(theme_key: str) -> dict:
    d = WIN_THEMES if IS_WIN else MAC_THEMES
    return d[theme_key]

def _font(key: str) -> int:
    return (WIN_FONTS if IS_WIN else MAC_FONTS).get(key, 11)

def _ff() -> str:
    return "Segoe UI" if IS_WIN else "SF Pro Display"

# Windows: Microsoft YaHei UI — native Chinese UI font, avoids mushy/thin Segoe fallback
WIN_FONT = "Microsoft YaHei UI"

def _sp(key: str) -> int:
    return (WIN_SPACE if IS_WIN else MAC_SPACE).get(key, 16)

def _sanitize_surrogates(text: str) -> str:
    return text.encode("utf-8", errors="surrogatepass").decode("utf-8", errors="replace")


# ──────────────────────────  ToastNotification  ───────────────────────────────

class ToastNotification:
    """
    Centered semi-transparent HUD overlay — fades in at the vertical center of the
    screen, lingers, then fades out.  Inspired by system-level HUD notifications
    (e.g. macOS volume indicator).

    Visual: frosted dark-navy pill, white text, no border chrome.
    """

    WIDTH = 340
    HEIGHT = 52
    ANIM_STEPS = 14
    ANIM_INTERVAL_MS = 16
    # Maximum alpha so the overlay stays translucent (not fully opaque)
    MAX_ALPHA = 0.82

    def __init__(self, root: tk.Tk, message: str, duration_ms: int = 2800,
                 accent: str | None = None, bg_color: str | None = None) -> None:
        self._root = root
        self._message = message
        self._duration_ms = duration_ms
        self._bg_color = bg_color or "#1a365d"
        self._win: Optional[tk.Toplevel] = None
        self._destroyed = False
        self._show()

    def _show(self) -> None:
        self._win = tk.Toplevel(self._root)
        win = self._win

        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.0)

        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        MARGIN = 24
        MENU_BAR_CLEAR = 50
        x = sw - self.WIDTH - MARGIN
        y = MENU_BAR_CLEAR

        win.geometry(f"{self.WIDTH}x{self.HEIGHT}+{x}+{y}")

        bg_color = self._bg_color
        win.configure(bg=bg_color)

        pill = tk.Frame(win, bg=bg_color)
        pill.place(x=0, y=0, width=self.WIDTH, height=self.HEIGHT)

        lbl = tk.Label(
            pill,
            text=self._message,
            font=(WIN_FONT if IS_WIN else _ff(), 11),
            bg=bg_color,
            fg="#ffffff",
            anchor="center",
        )
        lbl.place(relx=0.5, rely=0.5, anchor="center")

        self._animate_in(0)

    def _animate_in(self, step: int) -> None:
        if self._destroyed or not self._win:
            return
        alpha = (step / self.ANIM_STEPS) * self.MAX_ALPHA
        try:
            self._win.attributes("-alpha", alpha)
        except tk.TclError:
            return
        if step < self.ANIM_STEPS:
            self._win.after(self.ANIM_INTERVAL_MS, self._animate_in, step + 1)
        else:
            self._win.after(self._duration_ms, self._dismiss)

    def _dismiss(self) -> None:
        self._animate_out(0)

    def _animate_out(self, step: int) -> None:
        if self._destroyed or not self._win:
            return
        alpha = self.MAX_ALPHA * (1.0 - step / self.ANIM_STEPS)
        try:
            self._win.attributes("-alpha", alpha)
        except tk.TclError:
            return
        if step < self.ANIM_STEPS:
            self._win.after(self.ANIM_INTERVAL_MS, self._animate_out, step + 1)
        else:
            self._destroy()

    def _destroy(self) -> None:
        self._destroyed = True
        try:
            if self._win:
                self._win.destroy()
        except tk.TclError:
            pass


# ─────────────────────────  ToastQueue (serialised)  ─────────────────────────

class ToastQueue:
    """
    Ensures HUD toasts don't overlap — shows one at a time with a brief gap.
    """

    GAP_MS = 200

    def __init__(self, root: tk.Tk, get_toast_bg: Callable[[], str] | None = None) -> None:
        self._root = root
        self._pending: list[tuple[str, int, str | None]] = []
        self._busy = False
        self._get_toast_bg = get_toast_bg

    def push(self, message: str, duration_ms: int = 2800,
             accent: str | None = None, bg_color: str | None = None) -> None:
        self._pending.append((message, duration_ms, bg_color))
        if not self._busy:
            self._show_next()

    def _show_next(self) -> None:
        if not self._pending:
            self._busy = False
            return
        self._busy = True
        msg, duration, bg = self._pending.pop(0)
        if bg is None and self._get_toast_bg:
            bg = self._get_toast_bg()
        anim_total = ToastNotification.ANIM_STEPS * ToastNotification.ANIM_INTERVAL_MS * 2
        total_display = anim_total + duration
        ToastNotification(self._root, msg, duration_ms=duration, bg_color=bg)
        self._root.after(total_display + self.GAP_MS, self._show_next)


# ──────────────────────────────  PulsingDot  ─────────────────────────────────

class PulsingDot:
    """Animates a canvas oval between primary and primary_hover to simulate a pulse."""

    def __init__(self, canvas: tk.Canvas, x: int, y: int, r: int,
                 color: str, color_dim: str) -> None:
        self._canvas = canvas
        self._item = canvas.create_oval(x - r, y - r, x + r, y + r, fill=color, outline="")
        self._color = color
        self._color_dim = color_dim
        self._step = 0
        self._animate()

    def _animate(self) -> None:
        try:
            self._step += 1
            import math
            t = (self._step % 40) / 40.0
            alpha = (1 + math.sin(2 * math.pi * t - math.pi / 2)) / 2
            # Interpolate between color and color_dim
            r1, g1, b1 = int(self._color[1:3], 16), int(self._color[3:5], 16), int(self._color[5:7], 16)
            r2, g2, b2 = int(self._color_dim[1:3], 16), int(self._color_dim[3:5], 16), int(self._color_dim[5:7], 16)
            r = int(r1 + (r2 - r1) * (1 - alpha))
            g = int(g1 + (g2 - g1) * (1 - alpha))
            b = int(b1 + (b2 - b1) * (1 - alpha))
            color = f"#{r:02x}{g:02x}{b:02x}"
            self._canvas.itemconfig(self._item, fill=color)
            self._canvas.after(50, self._animate)
        except (tk.TclError, ValueError):
            pass


# ─────────────────────────  ProControlPanel  ─────────────────────────────────

STEP_LABELS = [
    "扫描群组列表",
    "筛选未读群组",
    "读取群消息",
    "识别可疑用户",
    "生成处理方案",
    "执行移除操作",
]
TOTAL_STEPS = len(STEP_LABELS)


class ProControlPanel:
    """Minimal premium control panel — one button, auto-start, floating toasts."""

    def __init__(self) -> None:
        self.root_dir = ROOT
        self.artifacts_dir = ROOT / "artifacts"
        self.state_path = self.artifacts_dir / "panel_state.json"
        self.state = load_state(self.state_path)

        self.server_process: Optional[subprocess.Popen] = None
        self.workflow_process: Optional[subprocess.Popen] = None
        self._system_status = "stopped"
        self._stop_requested = False
        self._current_step = 0
        self._theme_widgets: List[tuple] = []  # (widget, key, attr) for theme refresh

        self._build_ui()
        self.toasts = ToastQueue(self.root, get_toast_bg=lambda: self._C()["toast_bg"])

        self._log("Control panel initialized.")
        self._log(f"Project root: {self.root_dir}")
        self.root.after(600, self._auto_start_system)

    def _C(self) -> dict:
        """Current theme colors — platform-aware."""
        return _C_for(_resolve_theme(self.state.theme))

    # ─────────────────────────  UI construction  ──────────────────────────────

    def _build_ui(self) -> None:
        if IS_WIN:
            self._build_ui_windows()
        else:
            self._build_ui_mac()

    # ──────────────────────────  Windows layout  ──────────────────────────────
    # Design language: WeChat-companion — white, clean, thin dividers, green accent.
    # Uses ttk.Button for the CTA so it receives proper OS focus/hover rendering.

    def _build_ui_windows(self) -> None:
        from tkinter import ttk
        C = self._C()
        self._dividers_win: list[tk.Frame] = []  # for theme refresh

        self.root = tk.Tk()
        self.root.title("WeClaw 自动化助手")
        self.root.geometry("400x280")
        self.root.resizable(False, False)
        self.root.configure(bg=C["bg"])
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # ttk style setup
        style = ttk.Style(self.root)
        try:
            style.theme_use("vista")
        except tk.TclError:
            style.theme_use("clam")

        # Accent button: Microsoft YaHei UI, normal weight for clearer Chinese
        style.configure("Accent.TButton",
                        font=(WIN_FONT, 10, "normal"),
                        foreground="#ffffff",
                        background=C["accent"],
                        relief="flat",
                        padding=(0, 10),
                        anchor="center")
        style.map("Accent.TButton",
                  background=[("active", C["accent_hover"]),
                               ("disabled", C["surface_alt"])],
                  foreground=[("disabled", C["text_secondary"])])

        # No menubar — overflow ⋮ in header opens popup (modern/blended)
        self._overflow_menu = tk.Menu(self.root, tearoff=0)
        self._overflow_menu.add_command(label="显示主窗口", command=self._show_window)
        self._overflow_menu.add_separator()
        self._overflow_menu.add_command(label="退出", command=self._on_close)

        # ── Root outer padding ──
        self._outer = tk.Frame(self.root, bg=C["bg"])
        self._outer.pack(fill=tk.BOTH, expand=True, padx=20, pady=16)

        # ── Header: icon + title block + overflow + pulse dot ──
        self._header = tk.Frame(self._outer, bg=C["bg"])
        self._header.pack(fill=tk.X, pady=(0, 14))

        # App icon: 36×36, accent square with W mark
        self._logo_canvas = tk.Canvas(self._header, width=36, height=36,
                                      bg=C["bg"], highlightthickness=0)
        self._logo_canvas.pack(side=tk.LEFT, padx=(0, 11))
        self._logo_rect = self._logo_canvas.create_rectangle(
            0, 0, 36, 36, fill=C["accent"], outline="")
        self._logo_lines = []
        for xi, x in enumerate([9, 18, 27]):
            yt = 8 if xi == 1 else 11
            dx = 5
            self._logo_lines.append(self._logo_canvas.create_line(
                x, yt, x - dx, 27, fill="#ffffff", width=2, capstyle=tk.ROUND))
            self._logo_lines.append(self._logo_canvas.create_line(
                x, yt, x + dx, 27, fill="#ffffff", width=2, capstyle=tk.ROUND))

        # Title + subtitle stacked (Microsoft YaHei UI for clean Chinese)
        text_col = tk.Frame(self._header, bg=C["bg"])
        text_col.pack(side=tk.LEFT, anchor=tk.W)

        self._title_lbl = tk.Label(
            text_col, text="WeClaw",
            font=(WIN_FONT, 15, "bold"), bg=C["bg"], fg=C["text"])
        self._title_lbl.pack(anchor=tk.W)

        self._subtitle_lbl = tk.Label(
            text_col, text="AI 自动巡检助手",
            font=(WIN_FONT, 10), bg=C["bg"], fg=C["text_secondary"])
        self._subtitle_lbl.pack(anchor=tk.W)

        # Overflow ⋮ — blended menu trigger (no traditional menubar)
        def _show_overflow(e: tk.Event) -> None:
            btn = e.widget
            self._overflow_menu.tk_popup(btn.winfo_rootx(), btn.winfo_rooty() + btn.winfo_height())

        overflow_btn = tk.Label(
            self._header, text="⋮",
            font=(WIN_FONT, 14), bg=C["bg"], fg=C["text_secondary"],
            cursor="hand2", padx=4)
        overflow_btn.pack(side=tk.RIGHT, anchor=tk.CENTER)
        overflow_btn.bind("<Button-1>", _show_overflow)

        # Pulse dot
        dot_canvas = tk.Canvas(self._header, width=8, height=8,
                               bg=C["bg"], highlightthickness=0)
        dot_canvas.pack(side=tk.RIGHT, anchor=tk.CENTER)
        PulsingDot(dot_canvas, 4, 4, 3, C["dot_idle"], C["dot_pulse"])

        # ── Hairline divider ──
        div1 = tk.Frame(self._outer, bg=C["divider"], height=1)
        div1.pack(fill=tk.X, pady=(0, 12))
        self._dividers_win.append(div1)

        # ── Status area (flat, no border-box) ──
        self._card = tk.Frame(self._outer, bg=C["bg"])  # kept as ref for theme refresh
        self._card_inner = self._card
        self._card.pack(fill=tk.X, pady=(0, 4))

        status_row = tk.Frame(self._card, bg=C["bg"])
        status_row.pack(fill=tk.X, pady=(0, 2))

        self._status_var = tk.StringVar(value="正在初始化...")
        self._status_lbl = tk.Label(
            status_row, textvariable=self._status_var,
            font=(WIN_FONT, 10), bg=C["bg"], fg=C["text"], anchor=tk.W)
        self._status_lbl.pack(side=tk.LEFT)

        self._conn_var = tk.StringVar(value="")
        self._conn_lbl = tk.Label(
            status_row, textvariable=self._conn_var,
            font=(WIN_FONT, 10), bg=C["bg"], fg=C["text_secondary"])
        self._conn_lbl.pack(side=tk.RIGHT)

        # ── Another hairline before button ──
        div2 = tk.Frame(self._outer, bg=C["divider"], height=1)
        div2.pack(fill=tk.X, pady=(6, 10))
        self._dividers_win.append(div2)

        # ── CTA: full-width ttk.Button with green accent ──
        self._start_btn = ttk.Button(
            self._outer, text="启动巡检",
            style="Accent.TButton",
            state=tk.DISABLED,
            command=self._on_start_clicked)
        self._start_btn.pack(fill=tk.X, ipady=3)
        self._btn_enabled = False

        # ── Bottom row: theme + Mac chip + version ──
        bottom = tk.Frame(self._outer, bg=C["bg"])
        bottom.pack(fill=tk.X, pady=(12, 0))

        # Theme selector chips — normal weight, 10pt minimum for readable Chinese
        self._theme_btns: dict[str, tk.Label] = {}
        for val, lbl in [("light", "浅色"), ("dark", "深色"), ("system", "跟随系统")]:
            active = self.state.theme == val
            chip = tk.Label(
                bottom, text=lbl,
                font=(WIN_FONT, 10, "bold" if active else "normal"),
                bg=C["accent"] if active else C["surface_alt"],
                fg=C["accent_text"] if active else C["text_secondary"],
                padx=8, pady=3, cursor="hand2")
            chip.pack(side=tk.LEFT, padx=(0, 4))
            chip.bind("<Button-1>", lambda e, v=val: self._set_theme(v))
            self._theme_btns[val] = chip

        # Mac mode chip
        mac_active = self.state.force_mac_mode
        self._mac_chip = tk.Label(
            bottom, text="Mac 模式",
            font=(WIN_FONT, 10, "bold" if mac_active else "normal"),
            bg=C["accent"] if mac_active else C["surface_alt"],
            fg=C["accent_text"] if mac_active else C["text_secondary"],
            padx=8, pady=3, cursor="hand2")
        self._mac_chip.pack(side=tk.LEFT, padx=(0, 4))
        self._mac_chip.bind("<Button-1>", lambda e: self._toggle_mac())

        self._version_lbl = tk.Label(
            bottom, text="v1.0.0",
            font=(WIN_FONT, 10), bg=C["bg"], fg=C["text_secondary"])
        self._version_lbl.pack(side=tk.RIGHT)

        self._platform_lbl = None  # not shown on Windows separately

    # ──────────────────────────  Mac layout  ──────────────────────────────────

    def _build_ui_mac(self) -> None:
        C = self._C()

        self.root = tk.Tk()
        self.root.title("WeClaw 自动化助手")
        self.root.geometry("440x300")
        self.root.resizable(False, False)
        self.root.configure(bg=C["bg"])
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.attributes("-alpha", 0.98)

        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        win_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="窗口", menu=win_menu)
        win_menu.add_command(label="显示主窗口", command=self._show_window)
        win_menu.add_separator()
        win_menu.add_command(label="退出", command=self._on_close)

        logo_sz = 44
        self._logo_sz = logo_sz
        self._outer = tk.Frame(self.root, bg=C["bg"])
        self._outer.pack(fill=tk.BOTH, expand=True, padx=_sp("8"), pady=_sp("6"))

        self._header = tk.Frame(self._outer, bg=C["bg"])
        self._header.pack(fill=tk.X, pady=(0, _sp("6")))

        self._logo_canvas = tk.Canvas(self._header, width=logo_sz, height=logo_sz,
                                      bg=C["bg"], highlightthickness=0)
        self._logo_canvas.pack(side=tk.LEFT, padx=(0, _sp("4")))
        self._logo_rect = self._logo_canvas.create_rectangle(
            2, 2, logo_sz - 2, logo_sz - 2, fill=C["primary"], outline="", width=0)
        self._logo_lines = []
        for xi, x in enumerate([12, 22, 32]):
            yt = 12 if xi == 1 else 16
            self._logo_lines.append(self._logo_canvas.create_line(
                x, yt, x - 5, 32, fill=C["primary_contrast"], width=2.5, capstyle=tk.ROUND))
            self._logo_lines.append(self._logo_canvas.create_line(
                x, yt, x + 5, 32, fill=C["primary_contrast"], width=2.5, capstyle=tk.ROUND))

        text_block = tk.Frame(self._header, bg=C["bg"])
        text_block.pack(side=tk.LEFT, anchor=tk.W)
        self._title_lbl = tk.Label(
            text_block, text="WeClaw",
            font=(_ff(), _font("2xl"), "bold"), bg=C["bg"], fg=C["text"])
        self._title_lbl.pack(anchor=tk.W)
        self._subtitle_lbl = tk.Label(
            text_block, text="自动化助手  ·  AI 驱动  ·  实时防护",
            font=(_ff(), _font("sm")), bg=C["bg"], fg=C["text_secondary"])
        self._subtitle_lbl.pack(anchor=tk.W, pady=(2, 0))

        # Theme toggle (right side)
        theme_frame = tk.Frame(self._header, bg=C["bg"])
        theme_frame.pack(side=tk.RIGHT, anchor=tk.N, pady=2)
        tk.Label(theme_frame, text="主题", font=(_ff(), _font("xs")),
                 bg=C["bg"], fg=C["text_secondary"]).pack(side=tk.LEFT)
        self._theme_btns: dict[str, tk.Label] = {}
        for val, lbl in [("light", "浅"), ("dark", "深"), ("system", "系统")]:
            active = self.state.theme == val
            chip = tk.Label(
                theme_frame, text=lbl,
                font=(_ff(), _font("xs"), "bold"),
                bg=C["primary"] if active else C["border"],
                fg=C["primary_contrast"] if active else C["text_secondary"],
                padx=8, pady=3, cursor="hand2")
            chip.pack(side=tk.LEFT, padx=(4, 0))
            chip.bind("<Button-1>", lambda e, v=val: self._set_theme(v))
            self._theme_btns[val] = chip

        dot_canvas = tk.Canvas(self._header, width=10, height=10,
                               bg=C["bg"], highlightthickness=0)
        dot_canvas.pack(side=tk.RIGHT, anchor=tk.N, padx=(8, 0), pady=6)
        PulsingDot(dot_canvas, 5, 5, 4, C["dot_idle"], C["dot_pulse"])

        # Status card
        self._card = tk.Frame(self._outer, bg=C["surface"],
                             highlightbackground=C["border"], highlightthickness=1)
        self._card.pack(fill=tk.X, pady=(0, _sp("6")))
        self._card_inner = tk.Frame(self._card, bg=C["surface"])
        self._card_inner.pack(fill=tk.X, padx=_sp("4"), pady=_sp("3"))

        status_row = tk.Frame(self._card_inner, bg=C["surface"])
        status_row.pack(fill=tk.X)
        self._status_var = tk.StringVar(value="正在初始化...")
        self._status_lbl = tk.Label(
            status_row, textvariable=self._status_var,
            font=(_ff(), _font("base")), bg=C["surface"], fg=C["text"], anchor=tk.W)
        self._status_lbl.pack(side=tk.LEFT)
        self._conn_var = tk.StringVar(value="")
        self._conn_lbl = tk.Label(
            status_row, textvariable=self._conn_var,
            font=(_ff(), _font("sm")), bg=C["surface"], fg=C["text_secondary"])
        self._conn_lbl.pack(side=tk.RIGHT)

        # CTA — custom colored Label (Mac doesn't need ttk here)
        self._start_btn = tk.Label(
            self._outer, text="启动巡检",
            font=(_ff(), _font("xl"), "bold"),
            bg=C["surface"], fg=C["text_secondary"],
            pady=_sp("3"), cursor="arrow", anchor="center")
        self._start_btn.pack(fill=tk.X, pady=(0, _sp("4")))
        self._btn_enabled = False

        def _on_btn_click(e: tk.Event) -> None:
            if self._btn_enabled:
                self._on_start_clicked()
        def _on_btn_enter(e: tk.Event) -> None:
            if self._btn_enabled:
                self._start_btn.config(bg=self._C()["primary_hover"])
        def _on_btn_leave(e: tk.Event) -> None:
            if self._btn_enabled:
                self._start_btn.config(bg=self._C()["primary"])
        self._start_btn.bind("<Button-1>", _on_btn_click)
        self._start_btn.bind("<Enter>", _on_btn_enter)
        self._start_btn.bind("<Leave>", _on_btn_leave)

        # Bottom row
        bottom = tk.Frame(self._outer, bg=C["bg"])
        bottom.pack(fill=tk.X)
        self._platform_lbl = tk.Label(
            bottom, text="运行平台",
            font=(_ff(), _font("xs")), bg=C["bg"], fg=C["text_secondary"])
        self._platform_lbl.pack(side=tk.LEFT)
        self._mac_chip = tk.Label(
            bottom, text="Mac",
            font=(_ff(), _font("xs"), "bold"),
            bg=C["primary"] if self.state.force_mac_mode else C["border"],
            fg=C["primary_contrast"] if self.state.force_mac_mode else C["text_secondary"],
            padx=10, pady=3, cursor="hand2")
        self._mac_chip.pack(side=tk.LEFT, padx=(8, 0))
        self._mac_chip.bind("<Button-1>", lambda e: self._toggle_mac())
        self._version_lbl = tk.Label(
            bottom, text="v1.0.0",
            font=(_ff(), _font("xs")), bg=C["bg"], fg=C["text_secondary"])
        self._version_lbl.pack(side=tk.RIGHT)

    # ─────────────────────────  helpers  ──────────────────────────────────────

    def _set_status(self, text: str, color: str | None = None) -> None:
        self._status_var.set(text)
        self._status_lbl.config(fg=color or self._C()["text"])

    def _set_conn(self, text: str) -> None:
        self._conn_var.set(text)

    def _advance_step(self, step: int) -> None:
        self._current_step = step

    def _save_state(self) -> None:
        save_state(self.state, self.state_path)

    def _set_theme(self, theme: str) -> None:
        self.state.theme = theme
        self._save_state()
        self._apply_theme()

    def _apply_theme(self) -> None:
        C = self._C()
        if IS_WIN:
            self._apply_theme_windows(C)
        else:
            self._apply_theme_mac(C)

    def _apply_theme_windows(self, C: dict) -> None:
        from tkinter import ttk
        ff = "Segoe UI"
        self.root.configure(bg=C["bg"])
        self._outer.configure(bg=C["bg"])
        self._header.configure(bg=C["bg"])
        self._logo_canvas.configure(bg=C["bg"])
        self._logo_canvas.itemconfig(self._logo_rect, fill=C["accent"])
        for line in self._logo_lines:
            self._logo_canvas.itemconfig(line, fill="#ffffff")
        self._title_lbl.config(bg=C["bg"], fg=C["text"])
        self._subtitle_lbl.config(bg=C["bg"], fg=C["text_secondary"])
        self._card.configure(bg=C["bg"])
        self._card_inner.configure(bg=C["bg"])
        self._status_lbl.config(bg=C["bg"], fg=C["text"])
        self._conn_lbl.config(bg=C["bg"], fg=C["text_secondary"])
        self._version_lbl.config(bg=C["bg"], fg=C["text_secondary"])
        for div in self._dividers_win:
            div.configure(bg=C["divider"])
        for val, chip in self._theme_btns.items():
            active = self.state.theme == val
            chip.config(
                bg=C["accent"] if active else C["surface_alt"],
                fg=C["accent_text"] if active else C["text_secondary"],
                font=(WIN_FONT, 10, "bold" if active else "normal"),
            )
        mac_active = self.state.force_mac_mode
        self._mac_chip.config(
            bg=C["accent"] if mac_active else C["surface_alt"],
            fg=C["accent_text"] if mac_active else C["text_secondary"],
            font=(WIN_FONT, 10, "bold" if mac_active else "normal"),
        )
        style = ttk.Style(self.root)
        style.configure("Accent.TButton",
                        foreground="#ffffff", background=C["accent"])
        style.map("Accent.TButton",
                  background=[("active", C["accent_hover"]),
                               ("disabled", C["surface_alt"])],
                  foreground=[("disabled", C["text_secondary"])])

    def _apply_theme_mac(self, C: dict) -> None:
        self.root.configure(bg=C["bg"])
        self._outer.configure(bg=C["bg"])
        self._header.configure(bg=C["bg"])
        self._logo_canvas.configure(bg=C["bg"])
        self._logo_canvas.itemconfig(self._logo_rect, fill=C["primary"])
        for line in self._logo_lines:
            self._logo_canvas.itemconfig(line, fill=C["primary_contrast"])
        self._title_lbl.config(bg=C["bg"], fg=C["text"])
        self._subtitle_lbl.config(bg=C["bg"], fg=C["text_secondary"])
        self._status_lbl.config(bg=C["surface"], fg=C["text"])
        self._conn_lbl.config(bg=C["surface"], fg=C["text_secondary"])
        self._card.configure(bg=C["surface"], highlightbackground=C["border"])
        self._card_inner.configure(bg=C["surface"])
        if self._platform_lbl:
            self._platform_lbl.config(bg=C["bg"], fg=C["text_secondary"])
        self._version_lbl.config(bg=C["bg"], fg=C["text_secondary"])
        for val, chip in self._theme_btns.items():
            active = self.state.theme == val
            chip.config(
                bg=C["primary"] if active else C["border"],
                fg=C["primary_contrast"] if active else C["text_secondary"],
            )
        if self._btn_enabled:
            self._start_btn.config(bg=C["primary"], fg=C["primary_contrast"])
        else:
            self._start_btn.config(bg=C["surface"], fg=C["text_secondary"])
        mac_active = self.state.force_mac_mode
        self._mac_chip.config(
            bg=C["primary"] if mac_active else C["border"],
            fg=C["primary_contrast"] if mac_active else C["text_secondary"],
        )

    def _enable_start_btn(self) -> None:
        """Enable the CTA button, platform-aware."""
        self._btn_enabled = True
        C = self._C()
        if IS_WIN:
            self._start_btn.config(state=tk.NORMAL, text="启动巡检")
        else:
            self._start_btn.config(
                bg=C["primary"], fg=C["primary_contrast"],
                cursor="hand2", text="启动巡检")

    def _disable_start_btn(self, label: str = "巡检中...") -> None:
        """Disable the CTA button, platform-aware."""
        self._btn_enabled = False
        C = self._C()
        if IS_WIN:
            self._start_btn.config(state=tk.DISABLED, text=label)
        else:
            self._start_btn.config(
                bg=C["surface"], fg=C["text_secondary"],
                cursor="arrow", text=label)

    def _toggle_mac(self) -> None:
        self.state.force_mac_mode = not self.state.force_mac_mode
        C = self._C()
        active = self.state.force_mac_mode
        if IS_WIN:
            self._mac_chip.config(
                bg=C["accent"] if active else C["surface_alt"],
                fg=C["accent_text"] if active else C["text_secondary"],
                font=(WIN_FONT, 10, "bold" if active else "normal"),
            )
        else:
            self._mac_chip.config(
                bg=C["primary"] if active else C["border"],
                fg=C["primary_contrast"] if active else C["text_secondary"],
                font=(_ff(), _font("xs"), "bold" if active else "normal"),
            )
        self._save_state()

    def _toast(self, msg: str, duration_ms: int = 3000, accent: str | None = None) -> None:
        self.toasts.push(msg, duration_ms=duration_ms, accent=accent)

    def _log(self, message: str) -> None:
        """Print to terminal with timestamp."""
        timestamp = time.strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")

    # ─────────────────────────  system lifecycle  ─────────────────────────────

    def _auto_start_system(self) -> None:
        self._set_status("正在启动系统...")
        self._log("Starting system...")
        self._start_system()

    def _check_server_ready(self) -> bool:
        try:
            req = urllib.request.Request("http://localhost:8000/status", method="GET")
            with urllib.request.urlopen(req, timeout=2) as resp:
                return resp.status == 200
        except Exception:
            return False

    def _start_system(self) -> None:
        self._system_status = "starting_server"
        self._kill_workflow_processes()

        # Guard: port 8000 already in use
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(("0.0.0.0", 8000))
            s.close()
        except OSError as e:
            if "address already in use" in str(e).lower() or getattr(e, "errno", 0) == 10048:
                self._log("ERROR: Port 8000 is already in use!")
                self._set_status("端口 8000 已被占用", self._C()["error"])
                self._set_conn("× 启动失败")
                return
            raise

        vendor_server = self.root_dir / "vendor" / "computer-server"
        env = os.environ.copy()

        try:
            self.server_process = subprocess.Popen(
                [sys.executable, "-m", "computer_server", "--host", "0.0.0.0", "--port", "8000"],
                cwd=str(vendor_server),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
                creationflags=(subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0),
            )
        except Exception as e:
            self._log(f"Failed to start server: {e}")
            self._set_status(f"启动失败: {e}", self._C()["error"])
            return

        self._log("Starting computer-server...")
        startup_q: queue.Queue = queue.Queue()

        def _monitor():
            t0 = time.time()
            while self.server_process and time.time() - t0 < 30:
                if self.server_process.poll() is not None:
                    startup_q.put(("error",))
                    return
                if self._check_server_ready():
                    startup_q.put(("ready",))
                    return
                startup_q.put(("progress", int(time.time() - t0)))
                time.sleep(0.5)
            startup_q.put(("timeout",))

        def _poll():
            try:
                while True:
                    msg = startup_q.get_nowait()
                    if msg[0] == "ready":
                        self._log("Computer-server is ready.")
                        self._set_conn("● 已连接")
                        self._start_workflow_after_server()
                        return
                    if msg[0] in ("error", "timeout"):
                        self._log("Server process exited unexpectedly" if msg[0] == "error" else "Server startup timeout")
                        self._set_status("服务器启动失败", self._C()["error"])
                        self._set_conn("× 离线")
                        return
                    if msg[0] == "progress":
                        elapsed = msg[1]
                        self._set_status(f"正在启动服务器... ({elapsed}s)")
            except queue.Empty:
                pass
            self.root.after(200, _poll)

        threading.Thread(target=_monitor, daemon=True).start()
        self.root.after(200, _poll)

    def _start_workflow_after_server(self) -> None:
        self._system_status = "starting_workflow"
        self._set_status("正在加载工作流引擎...")
        self._log("Starting workflow backend...")

        use_mac = self.state.force_mac_mode or sys.platform == "darwin"
        cmd = [sys.executable, "-u", "-m", "workflow.run_wechat_removal", "--step-mode"]
        if use_mac:
            cmd.append("--mac")
            self._log("Starting workflow with Mac mode (full screen, AX tree)")
        else:
            self._log("Starting workflow with Windows mode (cropped regions)")

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        try:
            self.workflow_process = subprocess.Popen(
                cmd,
                cwd=str(self.root_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                creationflags=(subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0),
            )
        except Exception as e:
            self._log(f"Failed to start workflow: {e}")
            self._set_status(f"工作流启动失败: {e}", self._C()["error"])
            return

        wf_q: queue.Queue = queue.Queue()

        def _monitor_wf():
            assert self.workflow_process and self.workflow_process.stdout
            for line in self.workflow_process.stdout:
                decoded = line.decode("utf-8", errors="replace").strip()
                if decoded:
                    self._log(f"  [workflow] {decoded}")
                    if any(k in decoded for k in [
                        "STEP MODE ACTIVE", "Waiting for step requests",
                        "DESKTOP MODE", "Computer server connected",
                    ]):
                        wf_q.put(("running",))
            wf_q.put(("exited",))

        def _poll_wf():
            try:
                while True:
                    msg = wf_q.get_nowait()
                    if msg[0] == "running":
                        self._system_status = "running"
                        self._log("System is ready for workflow steps.")
                        self._set_status("就绪")
                        self._set_conn("● 已就绪")
                        self._btn_enabled = True
                        self._enable_start_btn()
                        return
                    if msg[0] == "exited":
                        self._log("Workflow process exited")
                        self._set_status("工作流已退出", self._C()["error"])
                        return
            except queue.Empty:
                pass
            if self.workflow_process:
                self.root.after(200, _poll_wf)

        threading.Thread(target=_monitor_wf, daemon=True).start()
        self.root.after(200, _poll_wf)

    def _stop_system(self) -> None:
        self._log("Stopping system...")
        for proc in (self.workflow_process, self.server_process):
            if proc:
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
        self.workflow_process = None
        self.server_process = None
        self._system_status = "stopped"
        self._log("System stopped.")

    # ─────────────────────────  workflow execution  ───────────────────────────

    def _on_start_clicked(self) -> None:
        if self._system_status != "running":
            return
        self._disable_start_btn("巡检中...")
        self._stop_requested = False
        self.root.after(800, self._hide_window)
        self._run_step_1_classify()

    def _request_agent_step(self, step: str, params: dict) -> None:
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self._log(f"Sending request: {step}")
        request_file = self.artifacts_dir / ".step_request"
        request_file.write_text(
            json.dumps({"step": step, "params": params}, ensure_ascii=False),
            encoding="utf-8",
        )

    def _poll_agent_result(self, callback: Callable[[dict], None]) -> None:
        result_file = self.artifacts_dir / ".step_result"
        status_file = self.artifacts_dir / ".step_status"
        aq: queue.Queue = queue.Queue()

        def _poll():
            start = time.time()
            count = 0
            while True:
                count += 1
                elapsed = time.time() - start
                if elapsed > 300:
                    aq.put(("timeout",))
                    return
                if self.workflow_process and self.workflow_process.poll() is not None:
                    aq.put(("exited",))
                    return
                if status_file.exists():
                    status = status_file.read_text(encoding="utf-8").strip()
                    if status == "complete" and result_file.exists():
                        raw = _sanitize_surrogates(result_file.read_text(encoding="utf-8"))
                        result = json.loads(raw)
                        result_file.unlink(missing_ok=True)
                        status_file.unlink(missing_ok=True)
                        aq.put(("result", result))
                        return
                    if status == "error":
                        err = result_file.read_text(encoding="utf-8") if result_file.exists() else "?"
                        result_file.unlink(missing_ok=True)
                        status_file.unlink(missing_ok=True)
                        aq.put(("error", err))
                        return
                time.sleep(0.5)

        def _drain():
            try:
                while True:
                    msg = aq.get_nowait()
                    if msg[0] == "result":
                        callback(msg[1])
                        return
                    if msg[0] in ("error", "timeout", "exited"):
                        label = {"error": "步骤出错", "timeout": "超时", "exited": "进程退出"}[msg[0]]
                        detail = f" — {msg[1]}" if len(msg) > 1 and msg[1] else ""
                        self._log(f"Agent error: {label}{detail}")
                        self._set_status(label, self._C()["error"])
                        self._toast(f"⚠ {label}")
                        self._finish_workflow(success=False)
                        return
            except queue.Empty:
                pass
            self.root.after(200, _drain)

        threading.Thread(target=_poll, daemon=True).start()
        self.root.after(200, _drain)

    def _finish_workflow(self, success: bool) -> None:
        self._enable_start_btn()
        if success:
            self._set_status("巡检完成")
            self._advance_step(TOTAL_STEPS)
            self._toast("✓ 巡检完成", duration_ms=4000)
        self._show_window()

    # ─────────────────────────  step chain  ───────────────────────────────────

    def _run_step_1_classify(self) -> None:
        self._advance_step(1)
        self._set_status(STEP_LABELS[0])
        self._toast("正在扫描微信群组列表...")
        self._request_agent_step("classify", {})
        self._poll_agent_result(self._on_classify_result)

    def _on_classify_result(self, result: dict) -> None:
        text_output = result.get("text", "")
        parse_height = result.get("parse_height")
        assert parse_height is not None, "parse_height missing"
        self.state.threads = parse_classification(text_output, image_height=parse_height)
        self.state.step_logs["classify"] = text_output
        self._save_state()
        self._run_step_2_filter()

    def _run_step_2_filter(self) -> None:
        self._advance_step(2)
        self._set_status(STEP_LABELS[1])
        self.state.unread_groups = filter_unread_groups(self.state.threads)
        self.state.current_thread_index = 0
        self._save_state()
        count = len(self.state.unread_groups)
        self._toast(f"发现 {count} 个未读群组")
        if not count:
            self._toast("当前无需处理的群组")
            self._finish_workflow(success=True)
            return
        self._run_step_3_read_messages()

    def _run_step_3_read_messages(self) -> None:
        idx = self.state.current_thread_index
        if idx >= len(self.state.unread_groups):
            self._run_step_6_complete()
            return
        self._advance_step(3)
        thread = self.state.unread_groups[idx]
        self._set_status(f"{STEP_LABELS[2]}  ·  {thread.name}")
        self._toast(f"正在读取「{thread.name}」的消息...")
        self.state.current_group_suspects = []
        self.state.current_group_plan = None
        self._save_state()
        self._request_agent_step(
            "read_messages",
            {"thread_id": thread.thread_id, "thread_name": thread.name, "y": thread.y},
        )
        self._poll_agent_result(self._on_read_result)

    def _on_read_result(self, result: dict) -> None:
        idx = self.state.current_thread_index
        thread = self.state.unread_groups[idx]
        self.state.step_logs[f"read_{thread.thread_id}"] = result.get("text", "")
        self.state.step_logs[f"read_{thread.thread_id}_screenshots"] = json.dumps(
            result.get("screenshots", [])
        )
        self._save_state()
        self._run_step_4_extract()

    def _run_step_4_extract(self) -> None:
        self._advance_step(4)
        idx = self.state.current_thread_index
        thread = self.state.unread_groups[idx]
        self._set_status(f"{STEP_LABELS[3]}  ·  {thread.name}")
        text_key = f"read_{thread.thread_id}"
        screenshots_key = f"read_{thread.thread_id}_screenshots"
        text_output = self.state.step_logs.get(text_key, "")
        screenshots = json.loads(self.state.step_logs.get(screenshots_key, "[]"))
        self.state.current_group_suspects = extract_suspects(
            thread, text_output, [Path(p) for p in screenshots]
        )
        self._save_state()
        count = len(self.state.current_group_suspects)
        self._toast(f"发现 {count} 名可疑用户" if count else "未发现可疑用户")
        self._run_step_5_plan()

    def _run_step_5_plan(self) -> None:
        self._advance_step(5)
        self._set_status(STEP_LABELS[4])
        self.state.current_group_plan = build_removal_plan(self.state.current_group_suspects)
        self._save_state()
        if not self.state.current_group_suspects:
            self._advance_to_next_group()
            return
        self._run_step_6_remove()

    def _run_step_6_remove(self) -> None:
        self._advance_step(6)
        idx = self.state.current_thread_index
        thread = self.state.unread_groups[idx]
        self._set_status(f"{STEP_LABELS[5]}  ·  {thread.name}")
        assert self.state.current_group_plan
        self.state.current_group_plan.confirmed = True
        self._save_state()

        suspects = self.state.current_group_suspects
        # Fire a toast per suspect (first 3 only to avoid flood)
        for s in suspects[:3]:
            self._toast(f"正在踢出 {s.sender_name}")
        if len(suspects) > 3:
            self._toast(f"以及另外 {len(suspects) - 3} 人...")

        suspect_data = [
            {"sender_id": s.sender_id, "sender_name": s.sender_name, "thread_id": s.thread_id}
            for s in suspects
        ]
        self._request_agent_step("remove", {"suspects": suspect_data})
        self._poll_agent_result(self._on_removal_result)

    def _on_removal_result(self, result: dict) -> None:
        removal_results = result.get("removal_results", [])
        success_count = sum(1 for r in removal_results if r.get("success"))
        if removal_results:
            self._toast(f"✓ 已踢出 {success_count} / {len(removal_results)} 人")
        idx = self.state.current_thread_index
        thread = self.state.unread_groups[idx]
        if self.state.current_group_plan:
            self.state.current_group_plan.note = result.get("text", "")
        self.state.step_logs[f"removal_{thread.thread_id}"] = result.get("text", "")
        self.state.step_logs[f"removal_{thread.thread_id}_results"] = json.dumps(removal_results)
        self._save_state()
        self._advance_to_next_group()

    def _advance_to_next_group(self) -> None:
        self.state.all_suspects.extend(self.state.current_group_suspects)
        if self.state.current_group_plan:
            self.state.all_plans.append(self.state.current_group_plan)
        self.state.suspects = list(self.state.all_suspects)
        self.state.current_thread_index += 1
        self.state.current_group_suspects = []
        self.state.current_group_plan = None
        self._save_state()

        if self.state.current_thread_index < len(self.state.unread_groups):
            self._run_step_3_read_messages()
        else:
            self._run_step_6_complete()

    def _run_step_6_complete(self) -> None:
        total = len(self.state.all_suspects)
        groups = len(self.state.all_plans)
        self._toast(f"✓ 全部 {groups} 个群组处理完毕，共踢出 {total} 人",
                    duration_ms=5000)
        self._finish_workflow(success=True)

    # ─────────────────────────  cleanup utilities  ────────────────────────────

    def _kill_workflow_processes(self) -> None:
        if sys.platform == "win32":
            try:
                result = subprocess.run(
                    ["wmic", "process", "where", "name='python.exe'",
                     "get", "processid,commandline"],
                    capture_output=True, text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                for line in result.stdout.splitlines():
                    if "run_wechat_removal" in line:
                        for part in reversed(line.strip().split()):
                            if part.isdigit():
                                subprocess.run(
                                    ["taskkill", "/F", "/T", "/PID", part],
                                    capture_output=True,
                                    creationflags=subprocess.CREATE_NO_WINDOW,
                                )
                                break
            except Exception:
                pass

    def _hide_window(self) -> None:
        """Withdraw window; re-open via menu bar: 窗口 -> 显示主窗口."""
        self.root.withdraw()

    def _show_window(self) -> None:
        """Show main window (from menu bar or when workflow completes)."""
        self.root.deiconify()
        self.root.lift()

    def _on_close(self) -> None:
        self._stop_requested = True
        self._stop_system()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    panel = ProControlPanel()
    panel.run()


if __name__ == "__main__":
    main()
