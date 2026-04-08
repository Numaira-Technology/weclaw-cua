"""Stepwise capture: screenshot sidebar + all visible chats, no LLM calls.

In --no-llm mode, the interactive click-scroll-LLM loop can't run because
each step depends on the previous LLM result (e.g., "which row to click?"
requires parsing the sidebar screenshot first).

This module captures everything we can without LLM:
  1. Full window screenshot
  2. Sidebar crop + SIDEBAR_PROMPT
  3. For the currently open chat: scroll-capture + stitch + CHAT_PANEL_PROMPT

The agent processes the vision tasks, then calls `weclaw finalize`.
"""

from __future__ import annotations

import os
import sys
import time

from config.weclaw_config import WeclawConfig
from shared.stepwise_backend import StepwiseBackend
from shared.vision_prompts import (
    CHAT_PANEL_PROMPT,
    MESSAGES_NAV_ICON_PROMPT,
    SIDEBAR_PROMPT,
)


def run_pipeline_a_stepwise(config: WeclawConfig, backend: StepwiseBackend) -> list[str]:
    """Capture screenshots and write vision tasks. No LLM calls, no clicking."""
    assert backend is not None
    os.makedirs(config.output_dir, exist_ok=True)

    if sys.platform == "darwin":
        return _run_mac_stepwise(config, backend)
    if sys.platform == "win32":
        return _run_win_stepwise(config, backend)
    raise NotImplementedError(f"Platform {sys.platform} not supported")


def _run_mac_stepwise(config: WeclawConfig, backend: StepwiseBackend) -> list[str]:
    from platform_mac.grant_permissions import ensure_permissions as grant_ax
    from platform_mac.find_wechat_window import find_wechat_window as locate_wechat
    from platform_mac.macos_window import (
        activate_pid,
        capture_window_pid,
    )

    grant_ax()
    ww = locate_wechat(config.wechat_app_name)
    pid = ww.pid
    print(f"[+] WeChat pid={pid}")

    activate_pid(pid)
    time.sleep(0.3)

    full_screenshot = capture_window_pid(pid)
    assert full_screenshot, "Failed to capture WeChat window"

    sidebar_width = int(full_screenshot.width * 0.3)
    sidebar_image = full_screenshot.crop((0, 0, sidebar_width, full_screenshot.height))
    print("[stepwise] Capturing sidebar for classification...")
    backend.query(SIDEBAR_PROMPT, sidebar_image)

    print("[stepwise] Capturing full window for nav icon detection...")
    backend.query(MESSAGES_NAV_ICON_PROMPT, full_screenshot, max_tokens=1024)

    chat_panel_x1 = int(full_screenshot.width * 0.31)
    chat_panel_y1 = 50
    chat_panel_x2 = int(full_screenshot.width * 0.95)
    chat_panel_y2 = full_screenshot.height - 50
    chat_panel = full_screenshot.crop((chat_panel_x1, chat_panel_y1, chat_panel_x2, chat_panel_y2))

    print("[stepwise] Capturing current chat panel for message extraction...")
    backend.query(CHAT_PANEL_PROMPT, chat_panel, max_tokens=16384)

    from platform_mac.chat_panel_scroll_capture import scroll_capture_frames_for_extraction

    class _MinimalDriver:
        def __init__(self, pid_val):
            self.pid = pid_val

        def scroll_chat_panel(self, direction="down"):
            from platform_mac import macos_window as _mw
            _mw.activate_pid(self.pid)
            time.sleep(0.08)
            clicks = 500 if direction == "up" else -500
            left, top, right, bottom = _mw.main_window_bounds(self.pid)
            mx = left + int((right - left) * 0.65)
            my = top + int((bottom - top) * 0.5)
            import pyautogui
            pyautogui.moveTo(mx, my, duration=0.1)
            pyautogui.scroll(clicks)
            time.sleep(1.15)

    driver_stub = _MinimalDriver(pid)
    print("[stepwise] Scroll-capturing chat frames...")
    frames = scroll_capture_frames_for_extraction(driver_stub, max_messages=None)

    if frames:
        frames.reverse()
        from utils.image_stitcher import stitch_screenshots
        chunk_size = 5
        chunks = [frames[i:i + chunk_size] for i in range(0, len(frames), chunk_size)]
        for i, chunk in enumerate(chunks):
            stitched = stitch_screenshots(images=chunk, scroll_region=None)
            if stitched:
                print(f"[stepwise] Capturing stitched chunk {i + 1}/{len(chunks)} for extraction...")
                backend.query(CHAT_PANEL_PROMPT, stitched, max_tokens=16384)

    print(f"\n[stepwise] Done. {len(backend.get_pending_tasks())} vision tasks saved.")
    print(f"[stepwise] Work dir: {backend.work_dir}")
    return []


def _run_win_stepwise(config: WeclawConfig, backend: StepwiseBackend) -> list[str]:
    from platform_win.find_wechat_window import find_wechat_window
    from platform_win.vision import capture_window, _force_foreground_window

    hwnd = find_wechat_window(app_name=config.wechat_app_name)
    assert hwnd, "WeChat window not found"
    print(f"[+] WeChat hwnd={hwnd}")

    _force_foreground_window(hwnd)
    time.sleep(0.3)

    full_screenshot = capture_window(hwnd)
    assert full_screenshot, "Failed to capture WeChat window"

    sidebar_width = int(full_screenshot.width * 0.3)
    sidebar_image = full_screenshot.crop((0, 0, sidebar_width, full_screenshot.height))
    print("[stepwise] Capturing sidebar for classification...")
    backend.query(SIDEBAR_PROMPT, sidebar_image)

    chat_panel_x1 = int(full_screenshot.width * 0.31)
    chat_panel_y1 = 50
    chat_panel_x2 = int(full_screenshot.width * 0.95)
    chat_panel_y2 = full_screenshot.height - 50
    chat_panel = full_screenshot.crop((chat_panel_x1, chat_panel_y1, chat_panel_x2, chat_panel_y2))

    print("[stepwise] Capturing current chat panel for message extraction...")
    backend.query(CHAT_PANEL_PROMPT, chat_panel, max_tokens=16384)

    print(f"\n[stepwise] Done. {len(backend.get_pending_tasks())} vision tasks saved.")
    print(f"[stepwise] Work dir: {backend.work_dir}")
    return []
