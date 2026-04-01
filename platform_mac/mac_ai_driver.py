"""macOS WeChat driver: screenshots + vision model parity with Windows WinDriver."""

import json
import time
from typing import Any

import pyautogui

from shared.datatypes import ChatMessage, SidebarRow
from shared.platform_api import PlatformDriver
from shared.sidebar_classification import parse_threads_json, threads_to_sidebar_rows
from shared.vision_ai import VisionAI
from shared.vision_response_json import parse_json_object_from_model_text
from shared.vision_prompts import COORDS_PROMPT_TEMPLATE, SIDEBAR_PROMPT
from platform_mac.find_wechat_window import find_wechat_window as locate_wechat
from platform_mac.grant_permissions import ensure_permissions as grant_ax
from platform_mac.mac_driver_messages import MacDriverMessages
from platform_mac.macos_window import (
    activate_pid,
    capture_window_pid,
    capture_window_pid_and_bounds,
    main_window_bounds,
    vision_bbox_center_to_screen_pt,
)


class MacDriver(MacDriverMessages, PlatformDriver):
    def __init__(self) -> None:
        self.pid: int = 0
        self.vision_ai = VisionAI()
        self._nav_messages_screen_pt: tuple[int, int] | None = None

    def ensure_permissions(self) -> None:
        grant_ax()

    def find_wechat_window(self, app_name: str = "WeChat") -> int:
        ww = locate_wechat(app_name)
        self.pid = ww.pid
        print(f"[+] WeChat '{app_name}' pid={self.pid}")
        return 1

    def _get_precise_row_coords(self, row: SidebarRow) -> tuple[int, int] | None:
        chat_name = row.name
        print(f"[*] Vision fallback: bbox for '{chat_name}' (full window)...")
        full_screenshot, wb = capture_window_pid_and_bounds(self.pid)
        img_width, img_height = full_screenshot.size
        prompt = COORDS_PROMPT_TEMPLATE.format(chat_name=chat_name)
        response_str = self.vision_ai.query(prompt, full_screenshot)
        if not response_str:
            return None
        data = parse_json_object_from_model_text(response_str)
        win_rel_bbox = data.get("bbox")
        if not win_rel_bbox or len(win_rel_bbox) != 4:
            return None
        center_x, center_y = vision_bbox_center_to_screen_pt(
            win_rel_bbox, img_width, img_height, wb
        )
        print(f"[+] Precise coordinates for '{chat_name}': ({center_x}, {center_y})")
        return (center_x, center_y)

    def get_sidebar_rows(self, window: Any) -> list[SidebarRow]:
        del window
        full_screenshot, wb = capture_window_pid_and_bounds(self.pid)
        sidebar_width = int(full_screenshot.width * 0.3)
        sidebar_image = full_screenshot.crop((0, 0, sidebar_width, full_screenshot.height))
        response_str = self.vision_ai.query(SIDEBAR_PROMPT, sidebar_image)
        if not response_str:
            return []
        try:
            threads = parse_threads_json(response_str)
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            print(f"[ERROR] Failed to parse sidebar classification JSON: {e}")
            print(f"Raw response was: {response_str}")
            return []
        img_width, img_height = sidebar_image.size
        fw, fh = full_screenshot.size
        sidebar_rows = threads_to_sidebar_rows(
            threads,
            img_width,
            img_height,
            wb.x,
            wb.y,
            full_window_width_px=fw,
            full_window_height_px=fh,
            window_width_pt=wb.width,
            window_height_pt=wb.height,
        )
        print(f"[+] AI identified {len(sidebar_rows)} sidebar rows.")
        return sidebar_rows

    def scroll_sidebar(self, window: Any, direction: str) -> None:
        del window
        assert self.pid
        assert direction in ("up", "down")
        activate_pid(self.pid)
        scroll_amount = 500
        clicks = scroll_amount if direction == "up" else -scroll_amount
        left, top, right, bottom = main_window_bounds(self.pid)
        sidebar_x = left + int((right - left) * 0.15)
        sidebar_y = top + int((bottom - top) * 0.5)
        print(f"[*] Scrolling sidebar {direction}...", end=" ")
        pyautogui.moveTo(sidebar_x, sidebar_y, duration=0.1)
        pyautogui.scroll(clicks)
        print("Done.")

    def get_row_name(self, row: Any) -> str:
        if not isinstance(row, SidebarRow):
            return ""
        return row.name

    def get_row_badge_text(self, row: Any) -> str | None:
        if not isinstance(row, SidebarRow):
            return None
        return row.badge_text

    def click_row(self, row: SidebarRow, attempt: int = 0) -> None:
        if not isinstance(row, SidebarRow):
            return
        x1, y1, x2, y2 = row.bbox
        if x2 > x1 and y2 > y1:
            center_x = (x1 + x2) // 2
            center_y = (y1 + y2) // 2 - 10 * attempt
            print(
                f"[*] Click row '{row.name}' via sidebar row bbox attempt {attempt + 1} "
                f"at ({center_x}, {center_y})"
            )
            pyautogui.moveTo(center_x, center_y, duration=0.25)
            pyautogui.click()
            return
        coords = self._get_precise_row_coords(row)
        if not coords:
            return
        center_x, center_y = coords
        adjusted_y = center_y + (-10 * attempt if attempt > 0 else 0)
        print(f"[*] Click row '{row.name}' vision fallback at ({center_x}, {adjusted_y})")
        pyautogui.moveTo(center_x, adjusted_y, duration=0.35)
        pyautogui.click()

    def get_message_elements(self, window: Any) -> list:
        del window
        return []

    def scroll_messages(self, window: Any, direction: str) -> None:
        del window
        assert self.pid
        assert direction in ("up", "down")
        activate_pid(self.pid)
        scroll_amount = 500
        clicks = scroll_amount if direction == "up" else -scroll_amount
        left, top, right, bottom = main_window_bounds(self.pid)
        message_panel_x = left + int((right - left) * 0.65)
        message_panel_y = top + int((bottom - top) * 0.5)
        pyautogui.moveTo(message_panel_x, message_panel_y, duration=0.1)
        pyautogui.scroll(clicks)

    def clear_messages_nav_click_cache(self) -> None:
        self._nav_messages_screen_pt = None

    def nav_messages_has_unread_badge(self) -> bool:
        assert self.pid
        from platform_mac.left_nav_messages_icon import nav_messages_unread_badge_present

        activate_pid(self.pid)
        full_screenshot, _ = capture_window_pid_and_bounds(self.pid)
        return nav_messages_unread_badge_present(full_screenshot)

    def double_click_messages_nav(self) -> None:
        assert self.pid
        from platform_mac.messages_nav_click_vision import resolve_messages_nav_screen_pt

        activate_pid(self.pid)
        if self._nav_messages_screen_pt is None:
            self._nav_messages_screen_pt = resolve_messages_nav_screen_pt(
                self.vision_ai, self.pid,
            )
        sx, sy = self._nav_messages_screen_pt
        pyautogui.moveTo(sx, sy, duration=0.12)
        pyautogui.doubleClick(interval=0.06)
        time.sleep(0.2)
