"""
Visual control panel for step-by-step workflow testing on desktop.

Usage:
  python control_panel.py

Input:
  - Project root directory (auto-detected).
  - Signal files for agent communication.

Output:
  - GUI with buttons for each workflow step.
  - State persistence in artifacts/panel_state.json.
  - Signal files for workflow backend communication.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import Callable, Optional

# Color palette - Minimalist White & Blue
COLORS = {
    "bg": "#ffffff",
    "bg_secondary": "#f8fafc",
    "card": "#f1f5f9",
    "primary": "#2563eb",
    "primary_hover": "#1d4ed8",
    "primary_light": "#dbeafe",
    "text": "#1e293b",
    "text_secondary": "#64748b",
    "border": "#e2e8f0",
    "status_running": "#2563eb",
    "status_stopped": "#94a3b8",
}


def _sanitize_surrogates(text: str) -> str:
    """Remove surrogate characters that cause UTF-8 encoding errors."""
    return text.encode("utf-8", errors="surrogatepass").decode(
        "utf-8", errors="replace"
    )


ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.group_classifier import parse_classification
from modules.removal_precheck import build_removal_plan
from modules.suspicious_detector import extract_suspects
from modules.task_types import GroupThread, RemovalPlan, Suspect
from modules.unread_scanner import filter_unread_groups
from panel_state import PanelState, _serialize_state, load_state, save_state


class LoadDataDialog:
    """Dialog for loading manual input data for a step."""

    def __init__(self, parent: tk.Tk, title: str, data_type: str, example_json: str):
        self.result = None
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(f"Load Data: {title}")
        self.dialog.geometry("500x400")
        self.dialog.configure(bg=COLORS["bg"])
        self.dialog.transient(parent)
        self.dialog.grab_set()

        style = ttk.Style()
        style.configure(
            "Dialog.TLabel", background=COLORS["bg"], foreground=COLORS["text"]
        )
        style.configure(
            "Dialog.TRadiobutton", background=COLORS["bg"], foreground=COLORS["text"]
        )

        main_frame = ttk.Frame(self.dialog, style="TFrame")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        ttk.Label(
            main_frame,
            text=f"Load {data_type} data:",
            style="Dialog.TLabel",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor=tk.W, pady=(0, 10))

        self.source_var = tk.StringVar(value="file")

        ttk.Radiobutton(
            main_frame,
            text="Load from file...",
            variable=self.source_var,
            value="file",
            style="Dialog.TRadiobutton",
        ).pack(anchor=tk.W, pady=2)

        ttk.Radiobutton(
            main_frame,
            text="Paste JSON:",
            variable=self.source_var,
            value="paste",
            style="Dialog.TRadiobutton",
        ).pack(anchor=tk.W, pady=2)

        self.json_text = scrolledtext.ScrolledText(
            main_frame,
            wrap=tk.WORD,
            font=("Consolas", 9),
            bg=COLORS["card"],
            fg=COLORS["text"],
            insertbackground=COLORS["text"],
            height=12,
            relief=tk.FLAT,
            borderwidth=0,
        )
        self.json_text.pack(fill=tk.BOTH, expand=True, pady=(10, 15))
        self.json_text.insert(tk.END, example_json)

        btn_frame = ttk.Frame(main_frame, style="TFrame")
        btn_frame.pack(fill=tk.X)

        ttk.Button(btn_frame, text="Cancel", command=self._cancel).pack(
            side=tk.RIGHT, padx=5
        )
        ttk.Button(
            btn_frame, text="Load", command=self._load, style="Primary.TButton"
        ).pack(side=tk.RIGHT)

        self.dialog.wait_window()

    def _cancel(self):
        self.result = None
        self.dialog.destroy()

    def _load(self):
        if self.source_var.get() == "file":
            filepath = filedialog.askopenfilename(
                parent=self.dialog,
                title="Select JSON file",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            )
            if filepath:
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        self.result = json.load(f)
                    self.dialog.destroy()
                except Exception as e:
                    messagebox.showerror(
                        "Error", f"Failed to load file: {e}", parent=self.dialog
                    )
            return
        else:
            try:
                self.result = json.loads(self.json_text.get("1.0", tk.END))
                self.dialog.destroy()
            except json.JSONDecodeError as e:
                messagebox.showerror("Error", f"Invalid JSON: {e}", parent=self.dialog)


class ControlPanel:
    def __init__(self):
        self.root_dir = ROOT
        self.artifacts_dir = self.root_dir / "artifacts"
        self.state_path = self.artifacts_dir / "panel_state.json"
        self.state = load_state(self.state_path)
        self.running_step: Optional[str] = None
        self.server_process: Optional[subprocess.Popen] = None
        self.workflow_process: Optional[subprocess.Popen] = None
        self._stop_requested: bool = False
        self._is_running: bool = False
        self._system_status: str = (
            "stopped"  # stopped, starting_server, starting_workflow, running
        )
        self._build_ui()

    def _build_ui(self) -> None:
        self.root = tk.Tk()
        self.root.title("WeChat Group Manager")
        self.root.geometry("1000x700")
        self.root.configure(bg=COLORS["bg"])
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Configure styles
        style = ttk.Style()
        style.theme_use("clam")

        # Base styles
        style.configure("TFrame", background=COLORS["bg"])
        style.configure(
            "TLabel",
            background=COLORS["bg"],
            foreground=COLORS["text"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "TButton",
            padding=(16, 8),
            font=("Segoe UI", 10),
            background=COLORS["card"],
            foreground=COLORS["text"],
        )
        style.map(
            "TButton",
            background=[("active", COLORS["border"])],
        )

        # Primary button style
        style.configure(
            "Primary.TButton",
            padding=(20, 10),
            font=("Segoe UI", 11, "bold"),
            background=COLORS["primary"],
            foreground="#ffffff",
        )
        style.map(
            "Primary.TButton",
            background=[
                ("active", COLORS["primary_hover"]),
                ("disabled", COLORS["border"]),
            ],
            foreground=[("disabled", COLORS["text_secondary"])],
        )

        # Secondary button style
        style.configure(
            "Secondary.TButton",
            padding=(12, 6),
            font=("Segoe UI", 9),
            background=COLORS["bg"],
            foreground=COLORS["text"],
        )
        style.map(
            "Secondary.TButton",
            background=[("active", COLORS["card"])],
        )

        # Step button style
        style.configure(
            "Step.TButton",
            padding=(12, 8),
            font=("Segoe UI", 10),
            background=COLORS["bg"],
            foreground=COLORS["text"],
        )
        style.map(
            "Step.TButton",
            background=[("active", COLORS["primary_light"])],
        )

        # Card frame style
        style.configure("Card.TFrame", background=COLORS["card"])

        # Header styles
        style.configure(
            "Title.TLabel",
            font=("Segoe UI", 24, "bold"),
            foreground=COLORS["text"],
            background=COLORS["bg"],
        )
        style.configure(
            "Subtitle.TLabel",
            font=("Segoe UI", 11),
            foreground=COLORS["text_secondary"],
            background=COLORS["bg"],
        )
        style.configure(
            "SectionHeader.TLabel",
            font=("Segoe UI", 12, "bold"),
            foreground=COLORS["text"],
            background=COLORS["bg"],
        )
        style.configure(
            "Status.TLabel",
            font=("Segoe UI", 10),
            foreground=COLORS["text_secondary"],
            background=COLORS["bg"],
        )

        # Main container
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=24, pady=20)

        # Header section
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 24))

        ttk.Label(header_frame, text="WeChat Group Manager", style="Title.TLabel").pack(
            anchor=tk.W
        )
        ttk.Label(
            header_frame,
            text="Automated spam detection and removal workflow",
            style="Subtitle.TLabel",
        ).pack(anchor=tk.W, pady=(4, 0))

        # Content area with sidebar
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill=tk.BOTH, expand=True)

        # Sidebar
        sidebar = ttk.Frame(content_frame, width=300)
        sidebar.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 20))
        sidebar.pack_propagate(False)

        # System Control Card
        self._create_system_control_card(sidebar)

        # Workflow Steps Card
        self._create_workflow_steps_card(sidebar)

        # Actions Card
        self._create_actions_card(sidebar)

        # Main content area
        content = ttk.Frame(content_frame)
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Status bar
        status_bar = ttk.Frame(content)
        status_bar.pack(fill=tk.X, pady=(0, 12))

        ttk.Label(status_bar, text="Status", style="SectionHeader.TLabel").pack(
            side=tk.LEFT
        )

        self.status_badge = tk.Label(
            status_bar,
            text="Ready",
            font=("Segoe UI", 9, "bold"),
            bg=COLORS["primary_light"],
            fg=COLORS["primary"],
            padx=12,
            pady=4,
        )
        self.status_badge.pack(side=tk.LEFT, padx=(12, 0))

        # Log area with card styling
        log_card = tk.Frame(content, bg=COLORS["card"], padx=2, pady=2)
        log_card.pack(fill=tk.BOTH, expand=True)

        self.log_area = scrolledtext.ScrolledText(
            log_card,
            wrap=tk.WORD,
            font=("Consolas", 10),
            bg=COLORS["card"],
            fg=COLORS["text"],
            insertbackground=COLORS["text"],
            relief=tk.FLAT,
            borderwidth=0,
            padx=12,
            pady=12,
        )
        self.log_area.pack(fill=tk.BOTH, expand=True)

        # State summary bar
        summary_frame = ttk.Frame(content)
        summary_frame.pack(fill=tk.X, pady=(12, 0))

        self.state_summary = ttk.Label(summary_frame, text="", style="Status.TLabel")
        self.state_summary.pack(side=tk.LEFT)

        self._update_state_summary()
        self._log("Control panel initialized.")
        self._log(f"Project root: {self.root_dir}")

    def _create_system_control_card(self, parent: ttk.Frame) -> None:
        """Create the system control card with merged Start/Stop button."""
        card = tk.Frame(parent, bg=COLORS["card"], padx=16, pady=16)
        card.pack(fill=tk.X, pady=(0, 16))

        # Header
        header = tk.Frame(card, bg=COLORS["card"])
        header.pack(fill=tk.X, pady=(0, 12))

        tk.Label(
            header,
            text="System Control",
            font=("Segoe UI", 12, "bold"),
            bg=COLORS["card"],
            fg=COLORS["text"],
        ).pack(side=tk.LEFT)

        # Status indicator
        self.system_status_dot = tk.Label(
            header,
            text="\u2022",
            font=("Segoe UI", 16),
            bg=COLORS["card"],
            fg=COLORS["status_stopped"],
        )
        self.system_status_dot.pack(side=tk.RIGHT)

        # Status text
        self.system_status_label = tk.Label(
            card,
            text="System stopped",
            font=("Segoe UI", 10),
            bg=COLORS["card"],
            fg=COLORS["text_secondary"],
        )
        self.system_status_label.pack(fill=tk.X, pady=(0, 12))

        # Running on Mac toggle
        self.force_mac_var = tk.BooleanVar(value=self.state.force_mac_mode)

        def _on_mac_toggle():
            self.state.force_mac_mode = self.force_mac_var.get()
            self._save_state()
            self._log(
                f"Mac mode: {'ON (full screen, AX tree)' if self.state.force_mac_mode else 'OFF (auto-detect)'}"
            )

        mac_frame = tk.Frame(card, bg=COLORS["card"])
        mac_frame.pack(fill=tk.X, pady=(0, 12))

        self.mac_toggle = tk.Checkbutton(
            mac_frame,
            text="Running on Mac",
            variable=self.force_mac_var,
            command=_on_mac_toggle,
            font=("Segoe UI", 10),
            bg=COLORS["card"],
            fg=COLORS["text"],
            activebackground=COLORS["card"],
            activeforeground=COLORS["text"],
            selectcolor=COLORS["primary_light"],
        )
        self.mac_toggle.pack(side=tk.LEFT)

        # Start/Stop button
        self.system_btn = ttk.Button(
            card,
            text="Start System",
            command=self._toggle_system,
            style="Primary.TButton",
        )
        self.system_btn.pack(fill=tk.X)

    def _create_workflow_steps_card(self, parent: ttk.Frame) -> None:
        """Create the workflow steps card with collapsible debug section."""
        card = tk.Frame(parent, bg=COLORS["card"], padx=16, pady=16)
        card.pack(fill=tk.X, pady=(0, 16))

        # Header with Debug toggle button
        header_frame = tk.Frame(card, bg=COLORS["card"])
        header_frame.pack(fill=tk.X, pady=(0, 8))

        tk.Label(
            header_frame,
            text="Workflow Steps",
            font=("Segoe UI", 12, "bold"),
            bg=COLORS["card"],
            fg=COLORS["text"],
        ).pack(side=tk.LEFT)

        self._debug_expanded = False
        self.debug_toggle_btn = ttk.Button(
            header_frame,
            text="Debug \u25bc",
            command=self._toggle_debug_steps,
            style="Secondary.TButton",
            width=8,
        )
        self.debug_toggle_btn.pack(side=tk.RIGHT)

        # Container for step buttons (initially hidden)
        self.steps_container = tk.Frame(card, bg=COLORS["card"])
        # Don't pack initially - hidden by default

        self.step_buttons = {}
        steps = [
            ("1. Classify Threads", "classify", self._run_classify, None),
            ("2. Filter Unread", "filter", self._run_filter, self._load_threads),
            ("3. Read Messages", "read", self._run_read_messages, self._load_groups),
            (
                "4. Extract Suspects",
                "extract",
                self._run_extract,
                self._load_read_results,
            ),
            ("5. Build Plan", "plan", self._run_build_plan, self._load_suspects),
            ("6. Execute Removal", "remove", self._run_removal, self._load_plan),
        ]

        for i, (label, step_id, callback, load_callback) in enumerate(steps):
            step_frame = tk.Frame(self.steps_container, bg=COLORS["card"])
            step_frame.pack(fill=tk.X, pady=2)

            btn = ttk.Button(
                step_frame, text=label, command=callback, style="Step.TButton", width=22
            )
            btn.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.step_buttons[step_id] = btn

            if load_callback:
                load_btn = ttk.Button(
                    step_frame,
                    text="\u2630",
                    command=load_callback,
                    width=3,
                    style="Secondary.TButton",
                )
                load_btn.pack(side=tk.RIGHT, padx=(4, 0))

    def _toggle_debug_steps(self) -> None:
        """Toggle visibility of debug workflow steps."""
        self._debug_expanded = not self._debug_expanded
        if self._debug_expanded:
            self.steps_container.pack(fill=tk.X, pady=(4, 0))
            self.debug_toggle_btn.config(text="Debug \u25b2")
        else:
            self.steps_container.pack_forget()
            self.debug_toggle_btn.config(text="Debug \u25bc")

    def _create_actions_card(self, parent: ttk.Frame) -> None:
        """Create the actions card."""
        card = tk.Frame(parent, bg=COLORS["card"], padx=16, pady=16)
        card.pack(fill=tk.X)

        tk.Label(
            card,
            text="Actions",
            font=("Segoe UI", 12, "bold"),
            bg=COLORS["card"],
            fg=COLORS["text"],
        ).pack(anchor=tk.W, pady=(0, 12))

        # Run All / Stop buttons
        run_frame = tk.Frame(card, bg=COLORS["card"])
        run_frame.pack(fill=tk.X, pady=(0, 8))

        self.run_all_btn = ttk.Button(
            run_frame,
            text="Run All Steps",
            command=self._run_all_steps,
            style="Primary.TButton",
        )
        self.run_all_btn.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.stop_btn = ttk.Button(
            run_frame,
            text="Stop",
            command=self._stop_execution,
            style="Secondary.TButton",
            state=tk.DISABLED,
        )
        self.stop_btn.pack(side=tk.RIGHT, padx=(8, 0))

        # Utility buttons
        ttk.Button(
            card,
            text="Reset State",
            command=self._reset_state,
            style="Secondary.TButton",
        ).pack(fill=tk.X, pady=(4, 0))

        ttk.Button(
            card,
            text="Export Report",
            command=self._export_report,
            style="Secondary.TButton",
        ).pack(fill=tk.X, pady=(4, 0))

    def _on_close(self) -> None:
        if self.workflow_process:
            self._stop_workflow()
        if self.server_process:
            self._stop_server()
        # Ensure port 8000 is released even if process tracking failed
        self._kill_port_8000()
        # Final cleanup of any orphaned workflow processes
        self._kill_workflow_processes()
        # Reset workflow state on exit; preserve Mac mode preference
        force_mac = self.state.force_mac_mode
        self.state = PanelState()
        self.state.force_mac_mode = force_mac
        self._save_state()
        self.root.destroy()

    def _kill_port_8000(self) -> None:
        """Kill any process using port 8000 to ensure clean shutdown."""
        if sys.platform == "win32":
            try:
                # Find PID using port 8000
                result = subprocess.run(
                    ["netstat", "-ano"],
                    capture_output=True,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                for line in result.stdout.splitlines():
                    if ":8000" in line and "LISTENING" in line:
                        parts = line.split()
                        if parts:
                            pid = parts[-1]
                            try:
                                subprocess.run(
                                    ["taskkill", "/F", "/PID", pid],
                                    capture_output=True,
                                    creationflags=subprocess.CREATE_NO_WINDOW,
                                )
                            except Exception:
                                pass
            except Exception:
                pass
        else:
            # Unix-like systems
            try:
                result = subprocess.run(
                    ["lsof", "-ti", ":8000"],
                    capture_output=True,
                    text=True,
                )
                pids = result.stdout.strip().split()
                for pid in pids:
                    if pid:
                        try:
                            subprocess.run(["kill", "-9", pid], capture_output=True)
                        except Exception:
                            pass
            except Exception:
                pass

    def _log(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.log_area.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_area.see(tk.END)

    def _set_status(self, status: str) -> None:
        self.status_badge.config(text=status)
        if "Error" in status:
            self.status_badge.config(bg="#fee2e2", fg="#dc2626")
        elif "Running" in status or "Run All" in status:
            self.status_badge.config(bg=COLORS["primary_light"], fg=COLORS["primary"])
        else:
            self.status_badge.config(bg=COLORS["card"], fg=COLORS["text_secondary"])

    def _update_system_status(self, status: str, message: str) -> None:
        """Update the system status display."""
        self._system_status = status

        if status == "stopped":
            self.system_status_dot.config(fg=COLORS["status_stopped"])
            self.system_status_label.config(text=message)
            self.system_btn.config(text="Start System", state=tk.NORMAL)
        elif status == "starting_server":
            self.system_status_dot.config(fg="#eab308")
            self.system_status_label.config(text=message)
            self.system_btn.config(text="Starting...", state=tk.DISABLED)
        elif status == "starting_workflow":
            self.system_status_dot.config(fg="#eab308")
            self.system_status_label.config(text=message)
            self.system_btn.config(text="Starting...", state=tk.DISABLED)
        elif status == "running":
            self.system_status_dot.config(fg=COLORS["status_running"])
            self.system_status_label.config(text=message)
            self.system_btn.config(text="Stop System", state=tk.NORMAL)
        elif status == "error":
            self.system_status_dot.config(fg="#ef4444")
            self.system_status_label.config(text=message)
            self.system_btn.config(text="Start System", state=tk.NORMAL)

    def _update_state_summary(self) -> None:
        idx = self.state.current_thread_index
        total = len(self.state.unread_groups)
        current_group_name = ""
        if idx < total:
            current_group_name = self.state.unread_groups[idx].name
        parts = [
            f"Threads: {len(self.state.threads)}",
            f"Groups: {idx}/{total}"
            + (f" ({current_group_name})" if current_group_name else ""),
            f"Current Suspects: {len(self.state.current_group_suspects)}",
            f"Total Suspects: {len(self.state.all_suspects)}",
        ]
        self.state_summary.config(text=" | ".join(parts))

    def _save_state(self) -> None:
        save_state(self.state, self.state_path)
        self._update_state_summary()

    def _reset_state(self) -> None:
        if messagebox.askyesno("Reset State", "Clear all workflow state?"):
            self.state = PanelState()
            self._save_state()
            self._log("State reset.")

    def _export_report(self) -> None:
        report_path = self.artifacts_dir / "logs" / "panel_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(_serialize_state(self.state), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._log(f"Report exported to {report_path}")
        messagebox.showinfo("Export", f"Report saved to:\n{report_path}")

    # System control methods (merged server + workflow)
    def _toggle_system(self) -> None:
        """Toggle the entire system (server + workflow)."""
        if self._system_status == "running":
            self._stop_system()
        elif self._system_status == "stopped" or self._system_status == "error":
            self._start_system()

    def _start_system(self) -> None:
        """Start the server, then automatically start the workflow."""
        self._update_system_status("starting_server", "Starting computer server...")
        self._log("Starting system...")

        # Kill any orphaned workflow processes from previous runs
        self._kill_workflow_processes()

        # Check if port 8000 is already in use
        import socket

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(("0.0.0.0", 8000))
            sock.close()
        except OSError as e:
            if e.errno == 10048 or "address already in use" in str(e).lower():
                self._log("ERROR: Port 8000 is already in use!")
                self._update_system_status("error", "Port 8000 in use")
                messagebox.showerror(
                    "Port In Use",
                    "Port 8000 is already in use.\n\n"
                    "Stop the existing server first.",
                )
                return
            else:
                raise

        self._log("Starting computer-server...")
        try:
            vendor_server = self.root_dir / "vendor" / "computer-server"
            env = os.environ.copy()

            self.server_process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "computer_server",
                    "--host",
                    "0.0.0.0",
                    "--port",
                    "8000",
                ],
                cwd=str(vendor_server),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
                creationflags=(
                    subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                ),
            )

            # Use a queue so the main thread drives UI updates. root.after(0, ...) from
            # a daemon thread does not run on macOS tkinter.
            server_startup_queue = queue.Queue()

            def monitor_and_start_workflow():
                start_time = time.time()
                iteration = 0

                while self.server_process and time.time() - start_time < 30:
                    iteration += 1
                    elapsed = time.time() - start_time
                    poll_result = self.server_process.poll()

                    if poll_result is not None:
                        server_startup_queue.put(("error", "Server failed to start"))
                        self.server_process = None
                        return

                    if self._check_server_ready():
                        server_startup_queue.put(("ready",))
                        return

                    server_startup_queue.put(("progress", int(elapsed)))
                    time.sleep(0.5)

                server_startup_queue.put(("timeout",))

            def _poll_server_startup_queue():
                try:
                    while True:
                        msg = server_startup_queue.get_nowait()
                        if msg[0] == "ready":
                            self._log("Computer-server is ready.")
                            self._start_workflow_after_server()
                            return
                        if msg[0] == "error":
                            self._update_system_status("error", msg[1])
                            self._log("Server process exited unexpectedly")
                            return
                        if msg[0] == "timeout":
                            self._update_system_status("error", "Server startup timeout")
                            return
                        if msg[0] == "progress":
                            self._update_system_status(
                                "starting_server",
                                f"Starting computer server... ({msg[1]}s)",
                            )
                except queue.Empty:
                    pass
                self.root.after(200, _poll_server_startup_queue)

            threading.Thread(target=monitor_and_start_workflow, daemon=True).start()
            self.root.after(200, _poll_server_startup_queue)

        except Exception as e:
            self._log(f"Failed to start server: {e}")
            self._update_system_status("error", "Failed to start server")
            messagebox.showerror("Error", f"Failed to start server: {e}")

    def _start_workflow_after_server(self) -> None:
        """Start the workflow after server is ready."""
        self._update_system_status("starting_workflow", "Starting workflow backend...")
        self._log("Starting workflow backend...")

        try:
            cmd = [
                sys.executable,
                "-u",
                "-m",
                "workflow.run_wechat_removal",
                "--step-mode",
            ]
            use_mac = self.state.force_mac_mode or sys.platform == "darwin"
            if use_mac:
                cmd.append("--mac")
                self._log("Starting workflow with Mac mode (full screen, AX tree)")
            else:
                self._log("Starting workflow with Windows mode (cropped regions)")
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            self.workflow_process = subprocess.Popen(
                cmd,
                cwd=str(self.root_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                creationflags=(
                    subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                ),
            )

            # Use queue so main thread drives UI; root.after(0,...) from thread fails on macOS
            workflow_queue = queue.Queue()
            workflow_start_time = time.time()

            def monitor_workflow():
                if self.workflow_process and self.workflow_process.stdout:
                    while self.workflow_process:
                        if self.workflow_process.poll() is not None:
                            exit_code = self.workflow_process.returncode
                            workflow_queue.put(("exited", exit_code))
                            self.workflow_process = None
                            return

                        line = self.workflow_process.stdout.readline()
                        if not line:
                            time.sleep(0.1)
                            continue

                        decoded = line.decode("utf-8", errors="replace").strip()
                        if decoded:
                            workflow_queue.put(("log", decoded))
                            if (
                                "STEP MODE ACTIVE" in decoded
                                or "Waiting for step requests" in decoded
                                or "DESKTOP MODE" in decoded
                                or "Computer server connected" in decoded
                            ):
                                workflow_queue.put(("running",))

            def _poll_workflow_queue():
                try:
                    while True:
                        msg = workflow_queue.get_nowait()
                        if msg[0] == "exited":
                            self._log(f"Workflow exited with code {msg[1]}")
                            self._update_system_status("error", "Workflow stopped")
                            return
                        if msg[0] == "log":
                            self._log(f"  [workflow] {msg[1]}")
                        if msg[0] == "running":
                            self._update_system_status("running", "System running")
                            self._log("System is ready for workflow steps.")
                except queue.Empty:
                    pass
                elapsed = time.time() - workflow_start_time
                if (
                    elapsed > 10
                    and self._system_status == "starting_workflow"
                    and self.workflow_process
                ):
                    self._update_system_status(
                        "starting_workflow",
                        "Starting workflow backend... (loading, may take 1–2 min on first run)",
                    )
                if self.workflow_process:
                    self.root.after(200, _poll_workflow_queue)

            threading.Thread(target=monitor_workflow, daemon=True).start()
            self.root.after(200, _poll_workflow_queue)

        except Exception as e:
            self._log(f"Failed to start workflow: {e}")
            self._update_system_status("error", "Failed to start workflow")
            # Stop server since workflow failed
            self._stop_server()

    def _stop_system(self) -> None:
        """Stop both workflow and server."""
        self._log("Stopping system...")

        if self.workflow_process:
            try:
                self.workflow_process.terminate()
                self.workflow_process.wait(timeout=5)
            except Exception:
                self.workflow_process.kill()
            self.workflow_process = None
            self._log("Workflow stopped.")

        if self.server_process:
            try:
                self.server_process.terminate()
                self.server_process.wait(timeout=5)
            except Exception:
                self.server_process.kill()
            self.server_process = None
            self._log("Server stopped.")

        self._update_system_status("stopped", "System stopped")

    def _check_server_ready(self) -> bool:
        """Check if computer-server is responding on port 8000."""
        try:
            req = urllib.request.Request("http://localhost:8000/status", method="GET")
            with urllib.request.urlopen(req, timeout=2) as resp:
                return resp.status == 200
        except Exception:
            return False

    # Legacy methods for compatibility
    def _toggle_server(self) -> None:
        if self.server_process:
            self._stop_server()
        else:
            self._start_server()

    def _start_server(self) -> None:
        # Redirect to system start
        self._start_system()

    def _stop_server(self) -> None:
        if self.server_process:
            try:
                self.server_process.terminate()
                self.server_process.wait(timeout=5)
            except Exception:
                try:
                    self.server_process.kill()
                except Exception:
                    pass
            self.server_process = None
        # Also kill any orphaned process on port 8000
        self._kill_port_8000()

    def _toggle_workflow(self) -> None:
        if self.workflow_process:
            self._stop_workflow()
        else:
            self._start_workflow()

    def _start_workflow(self) -> None:
        # Check if server is running first
        if not self._check_server_ready():
            messagebox.showwarning("Server Not Running", "Start the system first.")
            return
        self._start_workflow_after_server()

    def _stop_workflow(self) -> None:
        if self.workflow_process:
            pid = self.workflow_process.pid
            try:
                self.workflow_process.terminate()
                self.workflow_process.wait(timeout=3)
            except Exception:
                pass
            # Force kill the process tree on Windows
            self._kill_process_tree(pid)
            self.workflow_process = None
        # Also kill any orphaned workflow processes
        self._kill_workflow_processes()

    def _kill_process_tree(self, pid: int) -> None:
        """Kill a process and all its children on Windows."""
        if sys.platform == "win32":
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            except Exception:
                pass

    def _kill_workflow_processes(self) -> None:
        """Kill any Python processes running run_wechat_removal."""
        if sys.platform == "win32":
            try:
                # Use WMIC to find Python processes with our script
                result = subprocess.run(
                    [
                        "wmic",
                        "process",
                        "where",
                        "name='python.exe'",
                        "get",
                        "processid,commandline",
                    ],
                    capture_output=True,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                for line in result.stdout.splitlines():
                    if "run_wechat_removal" in line:
                        # Extract PID (last number in the line)
                        parts = line.strip().split()
                        for part in reversed(parts):
                            if part.isdigit():
                                try:
                                    subprocess.run(
                                        ["taskkill", "/F", "/T", "/PID", part],
                                        capture_output=True,
                                        creationflags=subprocess.CREATE_NO_WINDOW,
                                    )
                                except Exception:
                                    pass
                                break
            except Exception:
                pass

    def _run_all_steps(self) -> None:
        """Execute all workflow steps automatically in sequence."""
        if not self.workflow_process:
            messagebox.showwarning("System Not Running", "Start the system first.")
            return
        self._stop_requested = False
        self._is_running = True
        self.run_all_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self._log("=" * 50)
        self._log("Starting automated workflow execution...")
        self._log("=" * 50)
        self._run_all_classify()

    def _stop_execution(self) -> None:
        """Stop the automated workflow execution."""
        if not self._is_running:
            return
        self._stop_requested = True
        self._log("=" * 50)
        self._log("[Stop] Stop requested. Waiting for current step to complete...")
        self._log("=" * 50)
        self._set_status("Stopping...")

    def _check_stop_requested(self) -> bool:
        """Check if stop was requested and handle cleanup if so."""
        if self._stop_requested:
            self._log("[Stop] Workflow stopped by user.")
            self._set_status("Stopped")
            self._is_running = False
            self._stop_requested = False
            self.run_all_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)
            return True
        return False

    def _finish_run_all(self) -> None:
        """Clean up after run all completes or stops."""
        self._is_running = False
        self._stop_requested = False
        self.run_all_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)

    def _run_all_classify(self) -> None:
        """Step 1 of run all: Classify threads."""
        if self._check_stop_requested():
            return
        self._set_status("Run All: Classify Threads")
        self._log("[Run All] Step 1: Classifying threads...")
        self._request_agent_step("classify", {})
        self._poll_agent_result(self._run_all_on_classify_result)

    def _run_all_on_classify_result(self, result: dict) -> None:
        """Handle classify result and proceed to filter."""
        if self._check_stop_requested():
            return
        text_output = result.get("text", "")
        self._log(f"Classification output: {text_output[:200]}...")
        try:
            parse_height = result.get("parse_height")
            assert parse_height is not None, (
                "parse_height missing from classify result — re-run the Classify step."
            )
            self.state.threads = parse_classification(text_output, image_height=parse_height)
            self.state.step_logs["classify"] = text_output
            self._save_state()
            self._log(f"Parsed {len(self.state.threads)} threads.")
            self._run_all_filter()
        except Exception as e:
            self._log(f"Parse error: {e}")
            self._set_status("Error")
            self._log("[Run All] Stopped due to error.")
            self._finish_run_all()

    def _run_all_filter(self) -> None:
        """Step 2 of run all: Filter unread groups."""
        if self._check_stop_requested():
            return
        self._set_status("Run All: Filter Unread")
        self._log("[Run All] Step 2: Filtering unread groups...")
        self.state.unread_groups = filter_unread_groups(self.state.threads)
        self.state.current_thread_index = 0
        self._save_state()
        self._log(f"Found {len(self.state.unread_groups)} unread group(s).")
        for g in self.state.unread_groups:
            self._log(f"  - {g.name} (id={g.thread_id})")
        if not self.state.unread_groups:
            self._log("[Run All] No unread groups found. Workflow complete.")
            self._set_status("Ready")
            self._finish_run_all()
            messagebox.showinfo("Run All Complete", "No unread groups found.")
            return
        self._run_all_read_messages()

    def _run_all_read_messages(self) -> None:
        """Step 3 of run all: Read messages for current group."""
        if self._check_stop_requested():
            return
        idx = self.state.current_thread_index
        if idx >= len(self.state.unread_groups):
            self._run_all_complete()
            return
        self.state.current_group_suspects = []
        self.state.current_group_plan = None
        self._save_state()
        thread = self.state.unread_groups[idx]
        self._set_status(f"Run All: Read Messages ({thread.name})")
        self._log(
            f"[Run All] Step 3: Reading messages from {thread.name} ({idx + 1}/{len(self.state.unread_groups)})..."
        )
        self._request_agent_step(
            "read_messages",
            {"thread_id": thread.thread_id, "thread_name": thread.name, "y": thread.y},
        )
        self._poll_agent_result(self._run_all_on_read_result)

    def _run_all_on_read_result(self, result: dict) -> None:
        """Handle read result and proceed to extract."""
        if self._check_stop_requested():
            return
        text_output = result.get("text", "")
        screenshots = result.get("screenshots", [])
        self._log(f"Read result: {text_output[:200]}...")
        idx = self.state.current_thread_index
        thread = self.state.unread_groups[idx]
        self.state.step_logs[f"read_{thread.thread_id}"] = text_output
        self.state.step_logs[f"read_{thread.thread_id}_screenshots"] = json.dumps(
            screenshots
        )
        self._save_state()
        self._log(f"Read complete for {thread.name}.")
        self._run_all_extract()

    def _run_all_extract(self) -> None:
        """Step 4 of run all: Extract suspects from current group."""
        if self._check_stop_requested():
            return
        idx = self.state.current_thread_index
        thread = self.state.unread_groups[idx]
        self._set_status(f"Run All: Extract Suspects ({thread.name})")
        self._log(f"[Run All] Step 4: Extracting suspects from {thread.name}...")
        text_key = f"read_{thread.thread_id}"
        screenshots_key = f"read_{thread.thread_id}_screenshots"
        text_output = self.state.step_logs.get(text_key, "{}")
        screenshots_json = self.state.step_logs.get(screenshots_key, "[]")
        screenshot_paths = [Path(p) for p in json.loads(screenshots_json)]
        try:
            suspects = extract_suspects(thread, text_output, screenshot_paths)
            self.state.current_group_suspects = suspects
            self._save_state()
            self._log(f"Found {len(suspects)} suspect(s) in {thread.name}.")
            for s in suspects:
                self._log(f"  - {s.sender_name}: {s.evidence_text[:50]}...")
            self._run_all_build_plan()
        except Exception as e:
            self._log(f"Parse error: {e}")
            self._set_status("Error")
            self._log("[Run All] Stopped due to error.")
            self._finish_run_all()

    def _run_all_build_plan(self) -> None:
        """Step 5 of run all: Build removal plan for current group."""
        if self._check_stop_requested():
            return
        idx = self.state.current_thread_index
        thread = self.state.unread_groups[idx]
        self._set_status(f"Run All: Build Plan ({thread.name})")
        self._log(f"[Run All] Step 5: Building removal plan for {thread.name}...")
        self.state.current_group_plan = build_removal_plan(
            self.state.current_group_suspects
        )
        self._save_state()
        self._log(
            f"Plan created with {len(self.state.current_group_plan.suspects)} suspect(s)."
        )
        self._run_all_removal()

    def _run_all_removal(self) -> None:
        """Step 6 of run all: Execute removal for current group."""
        if self._check_stop_requested():
            return
        idx = self.state.current_thread_index
        thread = self.state.unread_groups[idx]
        if (
            not self.state.current_group_plan
            or not self.state.current_group_plan.suspects
        ):
            self._log(f"No suspects in {thread.name}. Advancing to next group.")
            self._run_all_advance_to_next_group()
            return
        self.state.current_group_plan.confirmed = True
        self._save_state()
        self._set_status(f"Run All: Execute Removal ({thread.name})")
        self._log(f"[Run All] Step 6: Executing removal for {thread.name}...")
        suspect_data = [
            {
                "sender_id": s.sender_id,
                "sender_name": s.sender_name,
                "thread_id": s.thread_id,
            }
            for s in self.state.current_group_plan.suspects
        ]
        self._request_agent_step("remove", {"suspects": suspect_data})
        self._poll_agent_result(self._run_all_on_removal_result)

    def _run_all_on_removal_result(self, result: dict) -> None:
        """Handle removal result and advance to next group."""
        if self._check_stop_requested():
            return
        text_output = result.get("text", "")
        idx = self.state.current_thread_index
        thread = self.state.unread_groups[idx]
        self._log(f"Removal result for {thread.name}: {text_output}")

        removal_results = result.get("removal_results", [])
        all_removed = result.get("all_removed", True)

        if removal_results:
            self._log("  Per-user results:")
            for r in removal_results:
                status = "SUCCESS" if r.get("success") else "FAILED"
                error = f" - {r.get('error')}" if r.get("error") else ""
                self._log(
                    f"    - {r.get('sender_name')}: {status} "
                    f"(attempts: {r.get('attempts', 1)}){error}"
                )

            if not all_removed:
                failed_names = [
                    r.get("sender_name")
                    for r in removal_results
                    if not r.get("success")
                ]
                self._log(f"  WARNING: Failed to remove: {', '.join(failed_names)}")

        if self.state.current_group_plan:
            self.state.current_group_plan.note = text_output
        self.state.step_logs[f"removal_{thread.thread_id}"] = text_output
        self.state.step_logs[f"removal_{thread.thread_id}_results"] = json.dumps(
            removal_results
        )
        self._save_state()
        self._run_all_advance_to_next_group()

    def _run_all_advance_to_next_group(self) -> None:
        """Advance to next group in run all mode."""
        self.state.all_suspects.extend(self.state.current_group_suspects)
        if self.state.current_group_plan:
            self.state.all_plans.append(self.state.current_group_plan)
        self.state.suspects = list(self.state.all_suspects)
        if self.state.all_plans:
            all_plan_suspects = []
            for p in self.state.all_plans:
                all_plan_suspects.extend(p.suspects)
            self.state.plan = RemovalPlan(
                suspects=all_plan_suspects,
                confirmed=True,
                note=f"Processed {len(self.state.all_plans)} group(s)",
            )
        self.state.current_thread_index += 1
        self.state.current_group_suspects = []
        self.state.current_group_plan = None
        self._save_state()
        if self._check_stop_requested():
            return
        remaining = len(self.state.unread_groups) - self.state.current_thread_index
        if remaining > 0:
            next_group = self.state.unread_groups[self.state.current_thread_index]
            self._log(
                f"[Run All] Advanced to next group. {remaining} group(s) remaining."
            )
            self._log(f"[Run All] Processing: {next_group.name}")
            self._run_all_read_messages()
        else:
            self._run_all_complete()

    def _run_all_complete(self) -> None:
        """Run all workflow complete."""
        self._log("=" * 50)
        self._log("[Run All] Workflow complete!")
        self._log(f"Total groups processed: {len(self.state.unread_groups)}")
        self._log(f"Total suspects found: {len(self.state.all_suspects)}")
        self._log(f"Total plans executed: {len(self.state.all_plans)}")
        self._log("=" * 50)
        self._set_status("Ready")
        self._finish_run_all()
        messagebox.showinfo(
            "Run All Complete",
            f"Automated workflow complete!\n\n"
            f"Groups processed: {len(self.state.unread_groups)}\n"
            f"Total suspects: {len(self.state.all_suspects)}\n\n"
            f"Click 'Export Report' to save results.",
        )

    # Manual data loading methods
    def _load_threads(self) -> None:
        example = json.dumps(
            [
                {
                    "thread_id": "g1",
                    "name": "Group Name",
                    "unread": True,
                    "is_group": True,
                },
                {
                    "thread_id": "c1",
                    "name": "Contact",
                    "unread": False,
                    "is_group": False,
                },
            ],
            ensure_ascii=False,
            indent=2,
        )
        dialog = LoadDataDialog(self.root, "Filter Unread", "threads", example)
        if dialog.result:
            try:
                self.state.threads = [
                    GroupThread(
                        name=t["name"],
                        thread_id=t["thread_id"],
                        unread=t["unread"],
                        is_group=t.get("is_group", True),
                    )
                    for t in dialog.result
                ]
                self._save_state()
                self._log(f"Loaded {len(self.state.threads)} threads manually.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to parse threads: {e}")

    def _load_groups(self) -> None:
        example = json.dumps(
            [
                {
                    "thread_id": "g1",
                    "name": "Group Name",
                    "unread": True,
                    "is_group": True,
                }
            ],
            ensure_ascii=False,
            indent=2,
        )
        dialog = LoadDataDialog(self.root, "Read Messages", "unread groups", example)
        if dialog.result:
            try:
                self.state.unread_groups = [
                    GroupThread(
                        name=g["name"],
                        thread_id=g["thread_id"],
                        unread=g["unread"],
                        is_group=g.get("is_group", True),
                    )
                    for g in dialog.result
                ]
                self.state.current_thread_index = 0
                self._save_state()
                self._log(
                    f"Loaded {len(self.state.unread_groups)} unread groups manually."
                )
            except Exception as e:
                messagebox.showerror("Error", f"Failed to parse groups: {e}")

    def _load_read_results(self) -> None:
        example = json.dumps(
            {
                "threads": [
                    {
                        "thread_id": "g1",
                        "name": "Group Name",
                        "unread": True,
                        "is_group": True,
                    }
                ],
                "read_results": {
                    "g1": {
                        "text": '{"suspects": []}',
                        "screenshots": [],
                    }
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        dialog = LoadDataDialog(self.root, "Extract Suspects", "read results", example)
        if dialog.result:
            try:
                threads_data = dialog.result.get("threads", [])
                self.state.unread_groups = [
                    GroupThread(
                        name=t["name"],
                        thread_id=t["thread_id"],
                        unread=t["unread"],
                        is_group=t.get("is_group", True),
                    )
                    for t in threads_data
                ]
                read_results = dialog.result.get("read_results", {})
                for tid, result in read_results.items():
                    self.state.step_logs[f"read_{tid}"] = result.get("text", "")
                    self.state.step_logs[f"read_{tid}_screenshots"] = json.dumps(
                        result.get("screenshots", [])
                    )
                self._save_state()
                self._log("Loaded read results manually.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to parse read results: {e}")

    def _load_suspects(self) -> None:
        example = json.dumps(
            [
                {
                    "sender_id": "wxid_xxx",
                    "sender_name": "Suspect Name",
                    "avatar_path": "",
                    "evidence_text": "Evidence text here",
                    "thread_id": "g1",
                }
            ],
            ensure_ascii=False,
            indent=2,
        )
        dialog = LoadDataDialog(self.root, "Build Plan", "suspects", example)
        if dialog.result:
            try:
                self.state.current_group_suspects = [
                    Suspect(
                        sender_id=s["sender_id"],
                        sender_name=s["sender_name"],
                        avatar_path=Path(s.get("avatar_path", "")),
                        evidence_text=s["evidence_text"],
                        thread_id=s["thread_id"],
                    )
                    for s in dialog.result
                ]
                self._save_state()
                self._log(
                    f"Loaded {len(self.state.current_group_suspects)} suspects manually."
                )
            except Exception as e:
                messagebox.showerror("Error", f"Failed to parse suspects: {e}")

    def _load_plan(self) -> None:
        example = json.dumps(
            {
                "suspects": [
                    {
                        "sender_id": "wxid_xxx",
                        "sender_name": "Suspect Name",
                        "thread_id": "g1",
                    }
                ],
                "confirmed": False,
                "note": "",
            },
            ensure_ascii=False,
            indent=2,
        )
        dialog = LoadDataDialog(self.root, "Execute Removal", "removal plan", example)
        if dialog.result:
            try:
                suspects_data = dialog.result.get("suspects", [])
                suspects = [
                    Suspect(
                        sender_id=s["sender_id"],
                        sender_name=s["sender_name"],
                        avatar_path=Path(s.get("avatar_path", "")),
                        evidence_text=s.get("evidence_text", ""),
                        thread_id=s.get("thread_id", ""),
                    )
                    for s in suspects_data
                ]
                self.state.current_group_plan = RemovalPlan(
                    suspects=suspects,
                    confirmed=dialog.result.get("confirmed", False),
                    note=dialog.result.get("note", ""),
                )
                self._save_state()
                self._log(
                    f"Loaded removal plan with {len(suspects)} suspects manually."
                )
            except Exception as e:
                messagebox.showerror("Error", f"Failed to parse plan: {e}")

    # Agent communication methods
    def _request_agent_step(self, step: str, params: dict) -> None:
        request_file = self.artifacts_dir / ".step_request"
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

        if self.workflow_process:
            poll_result = self.workflow_process.poll()
            if poll_result is not None:
                self._log(f"WARNING: Workflow process has exited (code {poll_result})")
                self._update_system_status("error", "Workflow stopped")
                self.workflow_process = None

        request_data = {"step": step, "params": params}
        self._log(f"Sending request: {step}")

        request_file.write_text(
            json.dumps(request_data, ensure_ascii=False),
            encoding="utf-8",
        )

    def _poll_agent_result(self, callback: Callable[[dict], None]) -> None:
        result_file = self.artifacts_dir / ".step_result"
        status_file = self.artifacts_dir / ".step_status"
        agent_result_queue = queue.Queue()

        def poll():
            poll_count = 0
            start_time = time.time()
            while True:
                poll_count += 1
                elapsed = time.time() - start_time

                if poll_count % 20 == 0:
                    agent_result_queue.put(("log", f"  Waiting for response... ({elapsed:.0f}s)"))
                    if self.workflow_process:
                        poll_result = self.workflow_process.poll()
                        if poll_result is not None:
                            agent_result_queue.put(("exited",))
                            return

                if elapsed > 300:
                    agent_result_queue.put(("timeout",))
                    return

                if status_file.exists():
                    status = status_file.read_text(encoding="utf-8").strip()

                    if status == "running":
                        pass
                    elif status == "complete" and result_file.exists():
                        result_text = result_file.read_text(encoding="utf-8")
                        result_text = _sanitize_surrogates(result_text)
                        result = json.loads(result_text)
                        result_file.unlink(missing_ok=True)
                        status_file.unlink(missing_ok=True)
                        agent_result_queue.put(("result", result))
                        return
                    elif status == "error":
                        error_msg = (
                            result_file.read_text(encoding="utf-8")
                            if result_file.exists()
                            else "Unknown error"
                        )
                        result_file.unlink(missing_ok=True)
                        status_file.unlink(missing_ok=True)
                        agent_result_queue.put(("error", error_msg))
                        return

                time.sleep(0.5)

        def _poll_agent_result_queue():
            try:
                while True:
                    msg = agent_result_queue.get_nowait()
                    if msg[0] == "log":
                        self._log(msg[1])
                    elif msg[0] == "result":
                        callback(msg[1])
                        return
                    elif msg[0] == "error":
                        self._on_agent_error(msg[1])
                        return
                    elif msg[0] == "timeout":
                        self._log("  TIMEOUT: No response after 5 minutes")
                        self._on_agent_error("Timeout waiting for response")
                        return
                    elif msg[0] == "exited":
                        self._log("  ERROR: Workflow process exited!")
                        self._on_agent_error("Workflow process exited")
                        return
            except queue.Empty:
                pass
            self.root.after(200, _poll_agent_result_queue)

        threading.Thread(target=poll, daemon=True).start()
        self.root.after(200, _poll_agent_result_queue)

    def _on_agent_error(self, error: str) -> None:
        self._set_status("Error")
        self._log(f"Agent error: {error}")
        self.running_step = None

    # Workflow step methods
    def _run_classify(self) -> None:
        if not self.workflow_process:
            messagebox.showwarning("System Not Running", "Start the system first.")
            return
        self._set_status("Running: Classify Threads")
        self._log("Starting thread classification...")
        self._request_agent_step("classify", {})
        self._poll_agent_result(self._on_classify_result)

    def _on_classify_result(self, result: dict) -> None:
        text_output = result.get("text", "")
        self._log(f"Classification output: {text_output[:200]}...")
        try:
            # parse_height is the pixel height of the image the AI saw.
            # The workflow backend always sets this correctly (1964 for Mac, 1440 for Windows).
            # There is intentionally no platform-specific fallback here — if it is absent
            # the caller should re-run classify so the backend provides the right value.
            parse_height = result.get("parse_height")
            assert parse_height is not None, (
                "parse_height missing from classify result — re-run the Classify step."
            )
            self.state.threads = parse_classification(text_output, image_height=parse_height)
            self.state.step_logs["classify"] = text_output
            self._save_state()
            self._log(f"Parsed {len(self.state.threads)} threads.")
            self._set_status("Ready")
        except Exception as e:
            self._log(f"Parse error: {e}")
            self._set_status("Error")

    def _run_filter(self) -> None:
        if not self.state.threads:
            messagebox.showwarning(
                "Missing Data", "Run 'Classify Threads' first or load threads manually."
            )
            return
        self._set_status("Running: Filter Unread")
        self._log("Filtering unread groups...")
        self.state.unread_groups = filter_unread_groups(self.state.threads)
        self.state.current_thread_index = 0
        self._save_state()
        self._log(f"Found {len(self.state.unread_groups)} unread group(s).")
        for g in self.state.unread_groups:
            self._log(f"  - {g.name} (id={g.thread_id})")
        self._set_status("Ready")

    def _run_read_messages(self) -> None:
        if not self.workflow_process:
            messagebox.showwarning("System Not Running", "Start the system first.")
            return
        if not self.state.unread_groups:
            messagebox.showwarning(
                "Missing Data", "Run 'Filter Unread' first or load groups manually."
            )
            return
        idx = self.state.current_thread_index
        if idx >= len(self.state.unread_groups):
            messagebox.showinfo("Complete", "All unread groups processed.")
            return
        self.state.current_group_suspects = []
        self.state.current_group_plan = None
        self._save_state()
        thread = self.state.unread_groups[idx]
        self._set_status(f"Running: Read Messages ({thread.name})")
        self._log(
            f"[Group {idx + 1}/{len(self.state.unread_groups)}] Reading: {thread.name}"
        )
        self._request_agent_step(
            "read_messages",
            {"thread_id": thread.thread_id, "thread_name": thread.name, "y": thread.y},
        )
        self._poll_agent_result(self._on_read_result)

    def _on_read_result(self, result: dict) -> None:
        text_output = result.get("text", "")
        screenshots = result.get("screenshots", [])
        self._log(f"Read result: {text_output[:200]}...")
        idx = self.state.current_thread_index
        thread = self.state.unread_groups[idx]
        self.state.step_logs[f"read_{thread.thread_id}"] = text_output
        self.state.step_logs[f"read_{thread.thread_id}_screenshots"] = json.dumps(
            screenshots
        )
        self._save_state()
        self._log(f"Read complete for {thread.name}.")
        self._set_status("Ready")

    def _run_extract(self) -> None:
        if not self.state.unread_groups:
            messagebox.showwarning(
                "Missing Data",
                "Run 'Read Messages' first or load read results manually.",
            )
            return
        idx = self.state.current_thread_index
        if idx >= len(self.state.unread_groups):
            messagebox.showinfo("Complete", "All unread groups processed.")
            return
        thread = self.state.unread_groups[idx]
        self._set_status(f"Running: Extract Suspects ({thread.name})")
        self._log(
            f"[Group {idx + 1}/{len(self.state.unread_groups)}] Extracting: {thread.name}"
        )
        text_key = f"read_{thread.thread_id}"
        screenshots_key = f"read_{thread.thread_id}_screenshots"
        text_output = self.state.step_logs.get(text_key, "{}")
        if text_output == "{}":
            messagebox.showwarning(
                "Missing Data",
                f"No read results for {thread.name}. Run 'Read Messages' first.",
            )
            return
        screenshots_json = self.state.step_logs.get(screenshots_key, "[]")
        screenshot_paths = [Path(p) for p in json.loads(screenshots_json)]
        try:
            suspects = extract_suspects(thread, text_output, screenshot_paths)
            self.state.current_group_suspects = suspects
            self._save_state()
            self._log(f"Found {len(suspects)} suspect(s) in {thread.name}:")
            for s in suspects:
                self._log(f"  - {s.sender_name}: {s.evidence_text[:50]}...")
        except Exception as e:
            self._log(f"Parse error: {e}")
        self._set_status("Ready")

    def _run_build_plan(self) -> None:
        idx = self.state.current_thread_index
        if idx >= len(self.state.unread_groups):
            messagebox.showinfo("Complete", "All unread groups processed.")
            return
        thread = self.state.unread_groups[idx]
        if not self.state.current_group_suspects:
            messagebox.showwarning(
                "Missing Data",
                f"No suspects found for {thread.name}. Run 'Extract Suspects' first.",
            )
            return
        self._set_status(f"Running: Build Plan ({thread.name})")
        self._log(
            f"[Group {idx + 1}/{len(self.state.unread_groups)}] Building plan: {thread.name}"
        )
        self.state.current_group_plan = build_removal_plan(
            self.state.current_group_suspects
        )
        self._save_state()
        self._log(
            f"Plan created with {len(self.state.current_group_plan.suspects)} suspect(s)."
        )
        self._set_status("Ready")

    def _run_removal(self) -> None:
        if not self.workflow_process:
            messagebox.showwarning("System Not Running", "Start the system first.")
            return
        idx = self.state.current_thread_index
        if idx >= len(self.state.unread_groups):
            messagebox.showinfo("Complete", "All unread groups processed.")
            return
        thread = self.state.unread_groups[idx]
        if not self.state.current_group_plan:
            messagebox.showwarning(
                "Missing Data", f"Run 'Build Plan' first for {thread.name}."
            )
            return
        if not self.state.current_group_plan.suspects:
            self._log(f"No suspects in {thread.name}. Advancing to next group.")
            self._advance_to_next_group()
            return
        confirm = messagebox.askyesno(
            "Confirm Removal",
            f"Remove {len(self.state.current_group_plan.suspects)} suspect(s) from {thread.name}?\n\n"
            + "\n".join(
                f"- {s.sender_name}" for s in self.state.current_group_plan.suspects
            ),
        )
        if not confirm:
            self._log("Removal cancelled. Advancing to next group.")
            self._advance_to_next_group()
            return
        self.state.current_group_plan.confirmed = True
        self._save_state()
        self._set_status(f"Running: Execute Removal ({thread.name})")
        self._log(
            f"[Group {idx + 1}/{len(self.state.unread_groups)}] Removing: {thread.name}"
        )
        suspect_data = [
            {
                "sender_id": s.sender_id,
                "sender_name": s.sender_name,
                "thread_id": s.thread_id,
            }
            for s in self.state.current_group_plan.suspects
        ]
        self._request_agent_step("remove", {"suspects": suspect_data})
        self._poll_agent_result(self._on_removal_result)

    def _on_removal_result(self, result: dict) -> None:
        text_output = result.get("text", "")
        idx = self.state.current_thread_index
        thread = self.state.unread_groups[idx]
        self._log(f"Removal result for {thread.name}: {text_output}")

        removal_results = result.get("removal_results", [])
        all_removed = result.get("all_removed", True)

        if removal_results:
            self._log("  Per-user results:")
            for r in removal_results:
                status = "SUCCESS" if r.get("success") else "FAILED"
                error = f" - {r.get('error')}" if r.get("error") else ""
                self._log(
                    f"    - {r.get('sender_name')}: {status} "
                    f"(attempts: {r.get('attempts', 1)}){error}"
                )

            if not all_removed:
                failed_names = [
                    r.get("sender_name")
                    for r in removal_results
                    if not r.get("success")
                ]
                self._log(f"  WARNING: Failed to remove: {', '.join(failed_names)}")

        if self.state.current_group_plan:
            self.state.current_group_plan.note = text_output
        self.state.step_logs[f"removal_{thread.thread_id}"] = text_output
        self.state.step_logs[f"removal_{thread.thread_id}_results"] = json.dumps(
            removal_results
        )
        self._save_state()
        self._advance_to_next_group()
        self._set_status("Ready")

    def _advance_to_next_group(self) -> None:
        """Save current group results and advance to the next unread group."""
        self.state.all_suspects.extend(self.state.current_group_suspects)
        if self.state.current_group_plan:
            self.state.all_plans.append(self.state.current_group_plan)
        self.state.suspects = list(self.state.all_suspects)
        if self.state.all_plans:
            all_plan_suspects = []
            for p in self.state.all_plans:
                all_plan_suspects.extend(p.suspects)
            self.state.plan = RemovalPlan(
                suspects=all_plan_suspects,
                confirmed=True,
                note=f"Processed {len(self.state.all_plans)} group(s)",
            )
        self.state.current_thread_index += 1
        self.state.current_group_suspects = []
        self.state.current_group_plan = None
        self._save_state()
        remaining = len(self.state.unread_groups) - self.state.current_thread_index
        if remaining > 0:
            next_group = self.state.unread_groups[self.state.current_thread_index]
            self._log(f"Advanced to next group. {remaining} group(s) remaining.")
            self._log(f"Next: {next_group.name}")
            messagebox.showinfo(
                "Group Complete",
                f"Finished processing current group.\n\n"
                f"{remaining} group(s) remaining.\n"
                f"Next: {next_group.name}\n\n"
                f"Click 'Read Messages' to continue.",
            )
        else:
            self._log("All groups processed!")
            self._log(f"Total suspects found: {len(self.state.all_suspects)}")
            self._log(f"Total plans executed: {len(self.state.all_plans)}")
            messagebox.showinfo(
                "Workflow Complete",
                f"All {len(self.state.unread_groups)} group(s) processed!\n\n"
                f"Total suspects: {len(self.state.all_suspects)}\n"
                f"Click 'Export Report' to save results.",
            )

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    panel = ControlPanel()
    panel.run()


if __name__ == "__main__":
    main()
