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

from modules.group_classifier import parse_classification
from modules.removal_precheck import build_removal_plan
from modules.suspicious_detector import extract_suspects
from modules.task_types import GroupThread, RemovalPlan, Suspect
from modules.unread_scanner import filter_unread_groups
from panel_state import PanelState, _serialize_state, load_state, save_state

# ─────────────────────────────  palette  ──────────────────────────────────────
C = {
    "bg": "#ffffff",
    "surface": "#f4f6f9",
    "navy": "#1a2744",
    "navy_dim": "#2d3d5c",
    "muted": "#8a95a3",
    "text": "#1a2744",
    "border": "#e4e8ef",
    "success": "#1a7a4a",
    "error": "#c0392b",
}

FONT_FAMILY = "SF Pro Display" if sys.platform == "darwin" else "Segoe UI"

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
                 accent: str | None = None) -> None:
        self._root = root
        self._message = message
        self._duration_ms = duration_ms
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

        # Dark frosted pill background
        bg_color = "#1a2744"
        win.configure(bg=bg_color)

        pill = tk.Frame(win, bg=bg_color)
        pill.place(x=0, y=0, width=self.WIDTH, height=self.HEIGHT)

        lbl = tk.Label(
            pill,
            text=self._message,
            font=(FONT_FAMILY, 12),
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

    def __init__(self, root: tk.Tk) -> None:
        self._root = root
        self._pending: list[tuple[str, int]] = []
        self._busy = False

    def push(self, message: str, duration_ms: int = 2800,
             accent: str | None = None) -> None:
        self._pending.append((message, duration_ms))
        if not self._busy:
            self._show_next()

    def _show_next(self) -> None:
        if not self._pending:
            self._busy = False
            return
        self._busy = True
        msg, duration = self._pending.pop(0)
        anim_total = ToastNotification.ANIM_STEPS * ToastNotification.ANIM_INTERVAL_MS * 2
        total_display = anim_total + duration
        ToastNotification(self._root, msg, duration_ms=duration)
        self._root.after(total_display + self.GAP_MS, self._show_next)


# ──────────────────────────────  PulsingDot  ─────────────────────────────────

class PulsingDot:
    """Animates a canvas oval between two alpha-equivalent colors to simulate a pulse."""

    def __init__(self, canvas: tk.Canvas, x: int, y: int, r: int,
                 color: str, bg: str) -> None:
        self._canvas = canvas
        self._item = canvas.create_oval(x - r, y - r, x + r, y + r, fill=color, outline="")
        self._colors = [color, bg]
        self._step = 0
        self._animate()

    def _animate(self) -> None:
        try:
            self._step += 1
            # pulse period: ~2 s (40 steps × 50 ms)
            t = (self._step % 40) / 40.0
            import math
            alpha = (1 + math.sin(2 * math.pi * t - math.pi / 2)) / 2
            r = int(0x1a + (0x2d - 0x1a) * (1 - alpha))
            g = int(0x27 + (0x3d - 0x27) * (1 - alpha))
            b = int(0x44 + (0x5c - 0x44) * (1 - alpha))
            color = f"#{r:02x}{g:02x}{b:02x}"
            self._canvas.itemconfig(self._item, fill=color)
            self._canvas.after(50, self._animate)
        except tk.TclError:
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

        self._build_ui()
        self.toasts = ToastQueue(self.root)

        # Auto-start system 600 ms after window renders
        self.root.after(600, self._auto_start_system)

    # ─────────────────────────  UI construction  ──────────────────────────────

    def _build_ui(self) -> None:
        self.root = tk.Tk()
        self.root.title("WeClaw 自动化助手")
        self.root.geometry("440x300")
        self.root.resizable(False, False)
        self.root.configure(bg=C["bg"])
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Semi-transparent window (WeChat-style title bar effect)
        self.root.attributes("-alpha", 0.97)

        # Menu bar — window can be re-opened via "窗口" -> "显示主窗口" when hidden
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        win_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="窗口", menu=win_menu)
        win_menu.add_command(label="显示主窗口", command=self._show_window)
        win_menu.add_separator()
        win_menu.add_command(label="退出", command=self._on_close)

        outer = tk.Frame(self.root, bg=C["bg"])
        outer.pack(fill=tk.BOTH, expand=True, padx=28, pady=24)

        # ── Header: logo + branding ──
        header = tk.Frame(outer, bg=C["bg"])
        header.pack(fill=tk.X, pady=(0, 18))

        # Square logo placeholder (40×40) — claw icon drawn with canvas
        logo_canvas = tk.Canvas(header, width=40, height=40, bg=C["bg"],
                                highlightthickness=0)
        logo_canvas.pack(side=tk.LEFT, padx=(0, 14))
        # Navy rounded square background
        logo_canvas.create_rectangle(2, 2, 38, 38, fill=C["navy"], outline="", width=0)
        # Stylised "W" / claw mark in white — three short downward strokes
        for offset, x in enumerate([10, 20, 30]):
            y_top = 10 if offset == 1 else 14
            logo_canvas.create_line(x, y_top, x - 4, 30, fill="#ffffff", width=2.5,
                                    capstyle=tk.ROUND)
            logo_canvas.create_line(x, y_top, x + 4, 30, fill="#ffffff", width=2.5,
                                    capstyle=tk.ROUND)

        # Branding text block
        text_block = tk.Frame(header, bg=C["bg"])
        text_block.pack(side=tk.LEFT, anchor=tk.W)

        tk.Label(
            text_block,
            text="WeClaw",
            font=(FONT_FAMILY, 20, "bold"),
            bg=C["bg"],
            fg=C["navy"],
        ).pack(anchor=tk.W)

        tk.Label(
            text_block,
            text="自动化助手  ·  AI 驱动  ·  实时防护",
            font=(FONT_FAMILY, 10),
            bg=C["bg"],
            fg=C["muted"],
        ).pack(anchor=tk.W, pady=(1, 0))

        # Pulsing dot — top-right of header
        dot_canvas = tk.Canvas(header, width=10, height=10, bg=C["bg"],
                               highlightthickness=0)
        dot_canvas.pack(side=tk.RIGHT, anchor=tk.N, pady=6)
        PulsingDot(dot_canvas, 5, 5, 4, C["navy"], C["bg"])

        # ── Status card ──
        card = tk.Frame(outer, bg=C["surface"])
        card.pack(fill=tk.X, pady=(0, 18))

        card_inner = tk.Frame(card, bg=C["surface"])
        card_inner.pack(fill=tk.X, padx=16, pady=12)

        # Status text row
        status_row = tk.Frame(card_inner, bg=C["surface"])
        status_row.pack(fill=tk.X)

        self._status_var = tk.StringVar(value="正在初始化...")
        self._status_lbl = tk.Label(
            status_row,
            textvariable=self._status_var,
            font=(FONT_FAMILY, 10),
            bg=C["surface"],
            fg=C["navy"],
            anchor=tk.W,
        )
        self._status_lbl.pack(side=tk.LEFT)

        self._conn_var = tk.StringVar(value="")
        tk.Label(
            status_row,
            textvariable=self._conn_var,
            font=(FONT_FAMILY, 10),
            bg=C["surface"],
            fg=C["muted"],
        ).pack(side=tk.RIGHT)

        # ── CTA button — implemented as a Label to guarantee color control on macOS ──
        self._start_btn = tk.Label(
            outer,
            text="启动巡检",
            font=(FONT_FAMILY, 13, "bold"),
            bg=C["surface"],
            fg=C["muted"],
            pady=12,
            cursor="arrow",
            anchor="center",
        )
        self._start_btn.pack(fill=tk.X, pady=(0, 16))
        self._btn_enabled = False

        def _on_btn_click(e: tk.Event) -> None:
            if self._btn_enabled:
                self._on_start_clicked()

        def _on_btn_enter(e: tk.Event) -> None:
            if self._btn_enabled:
                self._start_btn.config(bg=C["navy_dim"])

        def _on_btn_leave(e: tk.Event) -> None:
            if self._btn_enabled:
                self._start_btn.config(bg=C["navy"])

        self._start_btn.bind("<Button-1>", _on_btn_click)
        self._start_btn.bind("<Enter>", _on_btn_enter)
        self._start_btn.bind("<Leave>", _on_btn_leave)

        # ── Bottom row: platform chip + version ──
        bottom = tk.Frame(outer, bg=C["bg"])
        bottom.pack(fill=tk.X)

        tk.Label(bottom, text="运行平台", font=(FONT_FAMILY, 9),
                 bg=C["bg"], fg=C["muted"]).pack(side=tk.LEFT)

        # Mac chip — a small pill that lights up navy when active
        self._mac_chip = tk.Label(
            bottom,
            text="Mac",
            font=(FONT_FAMILY, 9, "bold"),
            bg=C["navy"] if self.state.force_mac_mode else C["border"],
            fg="#ffffff" if self.state.force_mac_mode else C["muted"],
            padx=10,
            pady=3,
            cursor="hand2",
        )
        self._mac_chip.pack(side=tk.LEFT, padx=(8, 0))
        self._mac_chip.bind("<Button-1>", lambda e: self._toggle_mac())

        tk.Label(bottom, text="v1.0.0", font=(FONT_FAMILY, 9),
                 bg=C["bg"], fg=C["muted"]).pack(side=tk.RIGHT)

    # ─────────────────────────  helpers  ──────────────────────────────────────

    def _set_status(self, text: str, color: str | None = None) -> None:
        self._status_var.set(text)
        self._status_lbl.config(fg=color or C["navy"])

    def _set_conn(self, text: str) -> None:
        self._conn_var.set(text)

    def _advance_step(self, step: int) -> None:
        self._current_step = step

    def _save_state(self) -> None:
        save_state(self.state, self.state_path)

    def _toggle_mac(self) -> None:
        self.state.force_mac_mode = not self.state.force_mac_mode
        if self.state.force_mac_mode:
            self._mac_chip.config(bg=C["navy"], fg="#ffffff")
        else:
            self._mac_chip.config(bg=C["border"], fg=C["muted"])
        self._save_state()

    def _toast(self, msg: str, duration_ms: int = 3000, accent: str | None = None) -> None:
        self.toasts.push(msg, duration_ms=duration_ms, accent=accent)

    # ─────────────────────────  system lifecycle  ─────────────────────────────

    def _auto_start_system(self) -> None:
        self._set_status("正在启动系统...")
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
                self._set_status("端口 8000 已被占用", C["error"])
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
            self._set_status(f"启动失败: {e}", C["error"])
            return

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
                        self._set_conn("● 已连接")
                        self._start_workflow_after_server()
                        return
                    if msg[0] in ("error", "timeout"):
                        self._set_status("服务器启动失败", C["error"])
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

        use_mac = self.state.force_mac_mode or sys.platform == "darwin"
        cmd = [sys.executable, "-u", "-m", "workflow.run_wechat_removal", "--step-mode"]
        if use_mac:
            cmd.append("--mac")

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
            self._set_status(f"工作流启动失败: {e}", C["error"])
            return

        wf_q: queue.Queue = queue.Queue()

        def _monitor_wf():
            assert self.workflow_process and self.workflow_process.stdout
            for line in self.workflow_process.stdout:
                decoded = line.decode("utf-8", errors="replace").strip()
                if decoded:
                    wf_q.put(("log", decoded))
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
                        self._set_status("就绪")
                        self._set_conn("● 已就绪")
                        self._btn_enabled = True
                        self._start_btn.config(
                            bg=C["navy"],
                            fg="#ffffff",
                            cursor="hand2",
                        )
                        return
                    if msg[0] == "exited":
                        self._set_status("工作流已退出", C["error"])
                        return
            except queue.Empty:
                pass
            if self.workflow_process:
                self.root.after(200, _poll_wf)

        threading.Thread(target=_monitor_wf, daemon=True).start()
        self.root.after(200, _poll_wf)

    def _stop_system(self) -> None:
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

    # ─────────────────────────  workflow execution  ───────────────────────────

    def _on_start_clicked(self) -> None:
        if self._system_status != "running":
            return
        self._btn_enabled = False
        self._start_btn.config(bg=C["surface"], fg=C["muted"], cursor="arrow", text="巡检中...")
        self._stop_requested = False
        # Hide window (withdraw) — re-open via menu bar: 窗口 -> 显示主窗口
        self.root.after(800, self._hide_window)
        self._run_step_1_classify()

    def _request_agent_step(self, step: str, params: dict) -> None:
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
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
                        self._set_status(label, C["error"])
                        self._toast(f"⚠ {label}")
                        self._finish_workflow(success=False)
                        return
            except queue.Empty:
                pass
            self.root.after(200, _drain)

        threading.Thread(target=_poll, daemon=True).start()
        self.root.after(200, _drain)

    def _finish_workflow(self, success: bool) -> None:
        self._btn_enabled = True
        self._start_btn.config(
            text="启动巡检",
            bg=C["navy"],
            fg="#ffffff",
            cursor="hand2",
        )
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
