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
        self.dialog.configure(bg="#1e1e1e")
        self.dialog.transient(parent)
        self.dialog.grab_set()

        style = ttk.Style()
        style.configure("Dialog.TLabel", background="#1e1e1e", foreground="#ffffff")
        style.configure(
            "Dialog.TRadiobutton", background="#1e1e1e", foreground="#ffffff"
        )

        main_frame = ttk.Frame(self.dialog, style="TFrame")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)

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
            bg="#2d2d2d",
            fg="#d4d4d4",
            insertbackground="#ffffff",
            height=12,
        )
        self.json_text.pack(fill=tk.BOTH, expand=True, pady=(5, 10))
        self.json_text.insert(tk.END, example_json)

        btn_frame = ttk.Frame(main_frame, style="TFrame")
        btn_frame.pack(fill=tk.X)

        ttk.Button(btn_frame, text="Cancel", command=self._cancel).pack(
            side=tk.RIGHT, padx=5
        )
        ttk.Button(btn_frame, text="Load", command=self._load).pack(side=tk.RIGHT)

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
        self._build_ui()

    def _build_ui(self) -> None:
        self.root = tk.Tk()
        self.root.title("WeChat Removal - Control Panel (Desktop Mode)")
        self.root.geometry("950x650")
        self.root.configure(bg="#1e1e1e")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#1e1e1e")
        style.configure("TLabel", background="#1e1e1e", foreground="#ffffff")
        style.configure("TButton", padding=8, font=("Segoe UI", 10))
        style.configure("Small.TButton", padding=4, font=("Segoe UI", 9))
        style.configure("Header.TLabel", font=("Segoe UI", 14, "bold"))
        style.configure("Status.TLabel", font=("Segoe UI", 9))
        style.configure("Server.TLabel", font=("Segoe UI", 9))

        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        sidebar = ttk.Frame(main_frame, width=280)
        sidebar.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        sidebar.pack_propagate(False)

        # Server controls section
        ttk.Label(sidebar, text="Server Control", style="Header.TLabel").pack(
            pady=(0, 10)
        )

        server_frame = ttk.Frame(sidebar)
        server_frame.pack(fill=tk.X, pady=(0, 5))
        self.server_btn = ttk.Button(
            server_frame, text="Start Server", command=self._toggle_server, width=15
        )
        self.server_btn.pack(side=tk.LEFT, padx=(0, 5))
        self.server_status = tk.Label(
            server_frame, text="Stopped", font=("Segoe UI", 9),
            bg="#1e1e1e", fg="#888888"
        )
        self.server_status.pack(side=tk.LEFT)

        workflow_frame = ttk.Frame(sidebar)
        workflow_frame.pack(fill=tk.X, pady=(0, 15))
        self.workflow_btn = ttk.Button(
            workflow_frame,
            text="Start Workflow",
            command=self._toggle_workflow,
            width=15,
        )
        self.workflow_btn.pack(side=tk.LEFT, padx=(0, 5))
        self.workflow_status = tk.Label(
            workflow_frame, text="Stopped", font=("Segoe UI", 9),
            bg="#1e1e1e", fg="#888888"
        )
        self.workflow_status.pack(side=tk.LEFT)

        ttk.Separator(sidebar, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        # Workflow steps section
        ttk.Label(sidebar, text="Workflow Steps", style="Header.TLabel").pack(
            pady=(0, 10)
        )

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

        for label, step_id, callback, load_callback in steps:
            step_frame = ttk.Frame(sidebar)
            step_frame.pack(fill=tk.X, pady=3)

            if load_callback:
                load_btn = ttk.Button(
                    step_frame,
                    text="📂",
                    command=load_callback,
                    width=3,
                    style="Small.TButton",
                )
                load_btn.pack(side=tk.LEFT, padx=(0, 5))

            btn = ttk.Button(step_frame, text=label, command=callback, width=20)
            btn.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.step_buttons[step_id] = btn

        ttk.Separator(sidebar, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=15)

        run_frame = ttk.Frame(sidebar)
        run_frame.pack(fill=tk.X, pady=5)
        self.run_all_btn = ttk.Button(
            run_frame, text="▶ Run All", command=self._run_all_steps, width=12
        )
        self.run_all_btn.pack(side=tk.LEFT, padx=(0, 5))
        self.stop_btn = ttk.Button(
            run_frame,
            text="■ Stop",
            command=self._stop_execution,
            width=10,
            state=tk.DISABLED,
        )
        self.stop_btn.pack(side=tk.LEFT)

        ttk.Separator(sidebar, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        ttk.Button(
            sidebar, text="Reset State", command=self._reset_state, width=25
        ).pack(pady=5)
        ttk.Button(
            sidebar, text="Export Report", command=self._export_report, width=25
        ).pack(pady=5)

        # Content area
        content = ttk.Frame(main_frame)
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        status_frame = ttk.Frame(content)
        status_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(status_frame, text="Status:", style="Header.TLabel").pack(
            side=tk.LEFT
        )
        self.status_label = ttk.Label(status_frame, text="Ready", style="Status.TLabel")
        self.status_label.pack(side=tk.LEFT, padx=10)

        self.log_area = scrolledtext.ScrolledText(
            content,
            wrap=tk.WORD,
            font=("Consolas", 10),
            bg="#2d2d2d",
            fg="#d4d4d4",
            insertbackground="#ffffff",
        )
        self.log_area.pack(fill=tk.BOTH, expand=True)

        state_frame = ttk.Frame(content)
        state_frame.pack(fill=tk.X, pady=(10, 0))

        self.state_summary = ttk.Label(state_frame, text="", style="Status.TLabel")
        self.state_summary.pack(side=tk.LEFT)

        self._update_state_summary()
        self._log("Control panel initialized (Desktop Mode).")
        self._log(f"Project root: {self.root_dir}")

    def _on_close(self) -> None:
        if self.workflow_process:
            self._stop_workflow()
        if self.server_process:
            self._stop_server()
        self.root.destroy()

    def _log(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.log_area.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_area.see(tk.END)

    def _set_status(self, status: str) -> None:
        self.status_label.config(text=status)

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

    def _run_all_steps(self) -> None:
        """Execute all workflow steps automatically in sequence."""
        if not self.workflow_process:
            messagebox.showwarning(
                "Workflow Not Running", "Start the workflow backend first."
            )
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
            self.state.threads = parse_classification(text_output)
            self.state.step_logs["classify"] = text_output
            self._save_state()
            self._log(f"Parsed {len(self.state.threads)} threads.")
            # Proceed to filter
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
        # Proceed to process first group
        self._run_all_read_messages()

    def _run_all_read_messages(self) -> None:
        """Step 3 of run all: Read messages for current group."""
        if self._check_stop_requested():
            return
        idx = self.state.current_thread_index
        if idx >= len(self.state.unread_groups):
            self._run_all_complete()
            return
        # Reset per-group state
        self.state.current_group_suspects = []
        self.state.current_group_plan = None
        self._save_state()
        thread = self.state.unread_groups[idx]
        self._set_status(f"Run All: Read Messages ({thread.name})")
        self._log(
            f"[Run All] Step 3: Reading messages from {thread.name} ({idx + 1}/{len(self.state.unread_groups)})..."
        )
        self._request_agent_step(
            "read_messages", {"thread_id": thread.thread_id, "thread_name": thread.name}
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
        # Proceed to extract
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
            # Proceed to build plan
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
        # Proceed to removal
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

        # Parse per-user removal results
        removal_results = result.get("removal_results", [])
        all_removed = result.get("all_removed", True)

        if removal_results:
            self._log(f"  Per-user results:")
            for r in removal_results:
                status = "SUCCESS" if r.get("success") else "FAILED"
                error = f" - {r.get('error')}" if r.get("error") else ""
                self._log(
                    f"    - {r.get('sender_name')}: {status} "
                    f"(attempts: {r.get('attempts', 1)}){error}"
                )

            if not all_removed:
                failed_names = [
                    r.get("sender_name") for r in removal_results if not r.get("success")
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
        # Accumulate results from current group
        self.state.all_suspects.extend(self.state.current_group_suspects)
        if self.state.current_group_plan:
            self.state.all_plans.append(self.state.current_group_plan)
        # Update legacy fields
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
        # Advance to next group
        self.state.current_thread_index += 1
        self.state.current_group_suspects = []
        self.state.current_group_plan = None
        self._save_state()
        # Check for stop before continuing to next group
        if self._check_stop_requested():
            return
        remaining = len(self.state.unread_groups) - self.state.current_thread_index
        if remaining > 0:
            next_group = self.state.unread_groups[self.state.current_thread_index]
            self._log(
                f"[Run All] Advanced to next group. {remaining} group(s) remaining."
            )
            self._log(f"[Run All] Processing: {next_group.name}")
            # Continue with next group
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

    # Server control methods
    def _toggle_server(self) -> None:
        if self.server_process:
            self._stop_server()
        else:
            self._start_server()

    def _check_server_ready(self) -> bool:
        """Check if computer-server is responding on port 8000."""
        try:
            req = urllib.request.Request("http://localhost:8000/status", method="GET")
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    return True
                return False
        except urllib.error.URLError:
            # Connection refused or other URL error - server not ready yet
            return False
        except Exception as e:
            # Unexpected error
            print(f"[_check_server_ready] Unexpected error: {type(e).__name__}: {e}")
            return False

    def _start_server(self) -> None:
        # Check if port 8000 is already in use
        import socket

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(("0.0.0.0", 8000))
            sock.close()
        except OSError as e:
            if e.errno == 10048 or "address already in use" in str(e).lower():
                self._log("ERROR: Port 8000 is already in use by another process!")
                self._log("  Please stop the existing server or use a different port.")
                messagebox.showerror(
                    "Port In Use",
                    "Port 8000 is already in use by another process.\n\n"
                    "Please stop the existing server before starting a new one.\n\n"
                    "On Windows, you can find the process with:\n"
                    "  netstat -ano | findstr :8000\n\n"
                    "Then kill it with:\n"
                    "  taskkill /F /PID <pid>",
                )
                return
            else:
                raise

        self._log("Starting computer-server...")
        self._log(
            f"  Working directory: {self.root_dir / 'vendor' / 'computer-server'}"
        )
        try:
            vendor_server = self.root_dir / "vendor" / "computer-server"

            # Set up environment with PYTHONPATH for imports
            env = os.environ.copy()

            self._log(
                f"  Command: {sys.executable} -m computer_server --host 0.0.0.0 --port 8000"
            )

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
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                creationflags=(
                    subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                ),
            )

            self.server_btn.config(text="Stop Server")
            self.server_status.config(text="Starting...", foreground="#eab308")
            self._log("Computer-server process started, waiting for ready...")

            # Start thread to monitor server output and readiness
            def monitor_server():
                ready = False
                start_time = time.time()
                check_count = 0

                while self.server_process and time.time() - start_time < 30:
                    check_count += 1
                    # Check if process is still running
                    if self.server_process.poll() is not None:
                        # Process exited
                        exit_code = self.server_process.returncode
                        output = (
                            self.server_process.stdout.read().decode(
                                "utf-8", errors="replace"
                            )
                            if self.server_process.stdout
                            else ""
                        )

                        self.root.after(
                            0,
                            lambda: self._log(
                                f"Server process exited with code {exit_code}"
                            ),
                        )
                        if output:
                            for line in output.split("\n")[:20]:  # First 20 lines
                                self.root.after(
                                    0, lambda l=line: self._log(f"  [server] {l}")
                                )
                        self.root.after(
                            0,
                            lambda: self.server_status.config(
                                text="Failed", foreground="#ef4444"
                            ),
                        )
                        self.server_process = None
                        return

                    # Check if server is responding
                    check_result = self._check_server_ready()
                    if check_count <= 3 or check_count % 10 == 0:
                        self.root.after(
                            0,
                            lambda c=check_count, r=check_result: self._log(
                                f"  Server check #{c}: {'ready' if r else 'not ready'}"
                            ),
                        )
                    if check_result:
                        # Verify our process is still alive (not detecting someone else's server)
                        if self.server_process.poll() is not None:
                            # Our process died, but something else is on port 8000
                            exit_code = self.server_process.returncode
                            output = (
                                self.server_process.stdout.read().decode(
                                    "utf-8", errors="replace"
                                )
                                if self.server_process.stdout
                                else ""
                            )

                            self.root.after(
                                0,
                                lambda: self._log(
                                    "ERROR: Server check succeeded but our process died!"
                                ),
                            )
                            self.root.after(
                                0,
                                lambda: self._log(
                                    f"Server process exited with code {exit_code}"
                                ),
                            )
                            if output:
                                for line in output.split("\n")[:20]:
                                    if line.strip():
                                        self.root.after(
                                            0,
                                            lambda l=line: self._log(f"  [server] {l}"),
                                        )
                            self.root.after(
                                0,
                                lambda: self._log(
                                    "This likely means another server is on port 8000."
                                ),
                            )
                            self.root.after(
                                0,
                                lambda: self.server_status.config(
                                    text="Failed", foreground="#ef4444"
                                ),
                            )
                            self.server_process = None
                            return

                        ready = True

                        self.root.after(
                            0,
                            lambda: self._log("Computer-server is ready on port 8000."),
                        )
                        self.root.after(
                            0,
                            lambda: self.server_status.config(
                                text="Running", foreground="#22c55e"
                            ),
                        )
                        break

                    time.sleep(0.5)

                if not ready and self.server_process:
                    self.root.after(
                        0,
                        lambda: self._log(
                            "Server startup timeout - may still be starting..."
                        ),
                    )
                    self.root.after(
                        0,
                        lambda: self.server_status.config(
                            text="Unknown", foreground="#eab308"
                        ),
                    )

                # Continue reading output in background
                if self.server_process and self.server_process.stdout:
                    while self.server_process:
                        line = self.server_process.stdout.readline()
                        if not line:
                            break
                        decoded = line.decode("utf-8", errors="replace").strip()
                        if decoded:
                            self.root.after(
                                0, lambda l=decoded: self._log(f"  [server] {l}")
                            )

            threading.Thread(target=monitor_server, daemon=True).start()

        except Exception as e:
            self._log(f"Failed to start server: {e}")
            import traceback

            self._log(f"  Traceback: {traceback.format_exc()}")
            messagebox.showerror("Error", f"Failed to start server: {e}")

    def _stop_server(self) -> None:
        if self.server_process:
            self._log("Stopping computer-server...")

            try:
                self.server_process.terminate()
                self.server_process.wait(timeout=5)

            except Exception as e:
                self._log(f"  Error during termination: {e}")
                self.server_process.kill()

            self.server_process = None
            self.server_btn.config(text="Start Server")
            self.server_status.config(text="Stopped", foreground="#888888")
            self._log("Computer-server stopped.")

    def _toggle_workflow(self) -> None:
        if self.workflow_process:
            self._stop_workflow()
        else:
            self._start_workflow()

    def _start_workflow(self) -> None:
        self._log("Starting workflow backend in step-mode...")
        self._log(f"  Working directory: {self.root_dir}")

        # Check if server is running first
        if not self._check_server_ready():
            self._log("WARNING: Computer-server does not appear to be running!")
            self._log("  The workflow may fail to connect. Start the server first.")

        try:
            self._log(
                f"  Command: {sys.executable} -u -m workflow.run_wechat_removal --step-mode"
            )

            self.workflow_process = subprocess.Popen(
                [
                    sys.executable,
                    "-u",
                    "-m",
                    "workflow.run_wechat_removal",
                    "--step-mode",
                ],
                cwd=str(self.root_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=(
                    subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                ),
            )

            self.workflow_btn.config(text="Stop Workflow")
            self.workflow_status.config(text="Starting...", foreground="#eab308")
            self._log("Workflow process started, monitoring output...")

            # Start thread to monitor workflow output
            def monitor_workflow():
                ready_seen = False
                if self.workflow_process and self.workflow_process.stdout:
                    while self.workflow_process:
                        # Check if process exited
                        if self.workflow_process.poll() is not None:
                            exit_code = self.workflow_process.returncode
                            remaining = self.workflow_process.stdout.read().decode(
                                "utf-8", errors="replace"
                            )
                            if remaining:
                                for line in remaining.split("\n"):
                                    if line.strip():
                                        self.root.after(
                                            0,
                                            lambda l=line: self._log(
                                                f"  [workflow] {l}"
                                            ),
                                        )
                            self.root.after(
                                0,
                                lambda: self._log(
                                    f"Workflow process exited with code {exit_code}"
                                ),
                            )
                            self.root.after(
                                0,
                                lambda: self.workflow_status.config(
                                    text="Stopped", foreground="#888888"
                                ),
                            )
                            self.root.after(
                                0,
                                lambda: self.workflow_btn.config(text="Start Workflow"),
                            )
                            self.workflow_process = None
                            return

                        line = self.workflow_process.stdout.readline()
                        if not line:
                            time.sleep(0.1)
                            continue

                        decoded = line.decode("utf-8", errors="replace").strip()
                        if decoded:
                            self.root.after(
                                0, lambda l=decoded: self._log(f"  [workflow] {l}")
                            )
                            if (
                                "STEP MODE ACTIVE" in decoded
                                or "Waiting for step requests" in decoded
                            ):
                                ready_seen = True
                                self.root.after(
                                    0,
                                    lambda: self.workflow_status.config(
                                        text="Running", foreground="#22c55e"
                                    ),
                                )
                                self.root.after(
                                    0,
                                    lambda: self._log(
                                        "Workflow backend is ready for step requests."
                                    ),
                                )

            threading.Thread(target=monitor_workflow, daemon=True).start()

        except Exception as e:
            self._log(f"Failed to start workflow: {e}")
            import traceback

            self._log(f"  Traceback: {traceback.format_exc()}")
            messagebox.showerror("Error", f"Failed to start workflow: {e}")

    def _stop_workflow(self) -> None:
        if self.workflow_process:
            self._log("Stopping workflow backend...")
            try:
                self.workflow_process.terminate()
                self.workflow_process.wait(timeout=5)
            except Exception as e:
                self._log(f"  Error during termination: {e}")
                self.workflow_process.kill()
            self.workflow_process = None
            self.workflow_btn.config(text="Start Workflow")
            self.workflow_status.config(text="Stopped", foreground="#888888")
            self._log("Workflow backend stopped.")

    # Manual data loading methods
    def _load_threads(self) -> None:
        example = json.dumps(
            [
                {
                    "thread_id": "g1",
                    "name": "留学交流群",
                    "unread": True,
                    "is_group": True,
                },
                {"thread_id": "c1", "name": "张三", "unread": False, "is_group": False},
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
                    "name": "留学交流群",
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
                        "name": "留学交流群",
                        "unread": True,
                        "is_group": True,
                    }
                ],
                "read_results": {
                    "g1": {
                        "text": '{"suspects": [{"sender_name": "代写论文", "sender_id": "wxid_xxx", "evidence": "专业代写"}]}',
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
                    "sender_name": "代写论文",
                    "avatar_path": "",
                    "evidence_text": "专业代写，联系微信xxx",
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
                    f"Loaded {len(self.state.current_group_suspects)} suspects manually (for current group)."
                )
            except Exception as e:
                messagebox.showerror("Error", f"Failed to parse suspects: {e}")

    def _load_plan(self) -> None:
        example = json.dumps(
            {
                "suspects": [
                    {
                        "sender_id": "wxid_xxx",
                        "sender_name": "代写论文",
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
                    f"Loaded removal plan with {len(suspects)} suspects manually (for current group)."
                )
            except Exception as e:
                messagebox.showerror("Error", f"Failed to parse plan: {e}")

    # Agent communication methods
    def _request_agent_step(self, step: str, params: dict) -> None:
        request_file = self.artifacts_dir / ".step_request"
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

        # Check if workflow is actually running
        if self.workflow_process:
            poll_result = self.workflow_process.poll()
            if poll_result is not None:
                self._log(f"WARNING: Workflow process has exited (code {poll_result})")
                self.workflow_status.config(text="Stopped", foreground="#888888")
                self.workflow_btn.config(text="Start Workflow")
                self.workflow_process = None

        request_data = {"step": step, "params": params}
        self._log(f"Writing request to: {request_file}")
        self._log(f"  Request data: {json.dumps(request_data, ensure_ascii=False)}")

        request_file.write_text(
            json.dumps(request_data, ensure_ascii=False),
            encoding="utf-8",
        )
        self._log(f"Sent request for step: {step}")
        self._log(
            f"  Waiting for response (status file: {self.artifacts_dir / '.step_status'})..."
        )

    def _poll_agent_result(self, callback: Callable[[dict], None]) -> None:
        result_file = self.artifacts_dir / ".step_result"
        status_file = self.artifacts_dir / ".step_status"

        self._log("  Polling for result...")
        self._log(f"    Status file: {status_file}")
        self._log(f"    Result file: {result_file}")

        def poll():
            poll_count = 0
            start_time = time.time()
            while True:
                poll_count += 1
                elapsed = time.time() - start_time

                # Log progress every 10 seconds
                if poll_count % 20 == 0:  # Every 10 seconds (0.5s * 20)
                    self.root.after(
                        0,
                        lambda e=elapsed: self._log(
                            f"  Still waiting for response... ({e:.0f}s elapsed)"
                        ),
                    )
                    # Check if workflow is still running
                    if self.workflow_process:
                        poll_result = self.workflow_process.poll()
                        if poll_result is not None:
                            self.root.after(
                                0,
                                lambda: self._log(
                                    "  ERROR: Workflow process exited unexpectedly!"
                                ),
                            )
                            self.root.after(
                                0,
                                lambda: self._on_agent_error("Workflow process exited"),
                            )
                            return

                # Timeout after 5 minutes
                if elapsed > 300:
                    self.root.after(
                        0, lambda: self._log("  TIMEOUT: No response after 5 minutes")
                    )
                    self.root.after(
                        0,
                        lambda: self._on_agent_error(
                            "Timeout waiting for agent response"
                        ),
                    )
                    return

                if status_file.exists():
                    status = status_file.read_text(encoding="utf-8").strip()
                    self.root.after(
                        0, lambda s=status: self._log(f"  Status file found: {s}")
                    )

                    if status == "running":
                        self.root.after(
                            0, lambda: self._log("  Agent is processing...")
                        )
                    elif status == "complete" and result_file.exists():
                        result_text = result_file.read_text(encoding="utf-8")
                        result_text = _sanitize_surrogates(result_text)
                        self.root.after(
                            0,
                            lambda: self._log(
                                f"  Result received ({len(result_text)} bytes)"
                            ),
                        )
                        result = json.loads(result_text)
                        result_file.unlink(missing_ok=True)
                        status_file.unlink(missing_ok=True)
                        self.root.after(0, lambda: callback(result))
                        return
                    elif status == "error":
                        error_msg = (
                            result_file.read_text(encoding="utf-8")
                            if result_file.exists()
                            else "Unknown error"
                        )
                        self.root.after(
                            0, lambda e=error_msg: self._log(f"  Error from agent: {e}")
                        )
                        result_file.unlink(missing_ok=True)
                        status_file.unlink(missing_ok=True)
                        self.root.after(0, lambda e=error_msg: self._on_agent_error(e))
                        return

                time.sleep(0.5)

        threading.Thread(target=poll, daemon=True).start()

    def _on_agent_error(self, error: str) -> None:
        self._set_status("Error")
        self._log(f"Agent error: {error}")
        self.running_step = None

    # Workflow step methods
    def _run_classify(self) -> None:
        if not self.workflow_process:
            messagebox.showwarning(
                "Workflow Not Running", "Start the workflow backend first."
            )
            return
        self._set_status("Running: Classify Threads")
        self._log("Starting thread classification...")
        self._request_agent_step("classify", {})
        self._poll_agent_result(self._on_classify_result)

    def _on_classify_result(self, result: dict) -> None:
        text_output = result.get("text", "")
        self._log(f"Classification output: {text_output[:200]}...")
        try:
            self.state.threads = parse_classification(text_output)
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
            messagebox.showwarning(
                "Workflow Not Running", "Start the workflow backend first."
            )
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
        # Reset per-group state when starting to read a new group
        self.state.current_group_suspects = []
        self.state.current_group_plan = None
        self._save_state()
        thread = self.state.unread_groups[idx]
        self._set_status(f"Running: Read Messages ({thread.name})")
        self._log(
            f"[Group {idx + 1}/{len(self.state.unread_groups)}] Reading messages from: {thread.name}"
        )
        self._request_agent_step(
            "read_messages", {"thread_id": thread.thread_id, "thread_name": thread.name}
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
        # Don't advance index here - wait until removal is complete for this group
        self._save_state()
        self._log(f"Read complete for {thread.name}. Proceed to Extract Suspects.")
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
            f"[Group {idx + 1}/{len(self.state.unread_groups)}] Extracting suspects from: {thread.name}"
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
            f"[Group {idx + 1}/{len(self.state.unread_groups)}] Building removal plan for: {thread.name}"
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
            messagebox.showwarning(
                "Workflow Not Running", "Start the workflow backend first."
            )
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
            self._log("Removal cancelled by user. Advancing to next group.")
            self._advance_to_next_group()
            return
        self.state.current_group_plan.confirmed = True
        self._save_state()
        self._set_status(f"Running: Execute Removal ({thread.name})")
        self._log(
            f"[Group {idx + 1}/{len(self.state.unread_groups)}] Executing removal for: {thread.name}"
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

        # Parse per-user removal results
        removal_results = result.get("removal_results", [])
        all_removed = result.get("all_removed", True)

        if removal_results:
            self._log(f"  Per-user results:")
            for r in removal_results:
                status = "SUCCESS" if r.get("success") else "FAILED"
                error = f" - {r.get('error')}" if r.get("error") else ""
                self._log(
                    f"    - {r.get('sender_name')}: {status} "
                    f"(attempts: {r.get('attempts', 1)}){error}"
                )

            if not all_removed:
                failed_names = [
                    r.get("sender_name") for r in removal_results if not r.get("success")
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
        # Accumulate results from current group
        self.state.all_suspects.extend(self.state.current_group_suspects)
        if self.state.current_group_plan:
            self.state.all_plans.append(self.state.current_group_plan)
        # Also update legacy fields for backward compatibility
        self.state.suspects = list(self.state.all_suspects)
        if self.state.all_plans:
            # Merge all plans into one for legacy compatibility
            all_plan_suspects = []
            for p in self.state.all_plans:
                all_plan_suspects.extend(p.suspects)
            self.state.plan = RemovalPlan(
                suspects=all_plan_suspects,
                confirmed=True,
                note=f"Processed {len(self.state.all_plans)} group(s)",
            )
        # Advance to next group
        self.state.current_thread_index += 1
        # Reset per-group state
        self.state.current_group_suspects = []
        self.state.current_group_plan = None
        self._save_state()
        remaining = len(self.state.unread_groups) - self.state.current_thread_index
        if remaining > 0:
            next_group = self.state.unread_groups[self.state.current_thread_index]
            self._log(f"Advanced to next group. {remaining} group(s) remaining.")
            self._log(
                f"Next group: {next_group.name}. Click 'Read Messages' to continue."
            )
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
