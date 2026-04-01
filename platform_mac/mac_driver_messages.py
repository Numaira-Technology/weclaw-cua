"""macOS：聊天区消息提取、侧栏当前会话名、新消息按钮。"""

import os
import time
from typing import TYPE_CHECKING

import pyautogui

from shared.datatypes import ChatMessage
from shared.vision_response_json import parse_json_object_from_model_text
from shared.vision_prompts import (
    CHAT_PANEL_PROMPT, CHAT_PANEL_SAFE_CLICK_PROMPT, CURRENT_CHAT_PROMPT, NEW_MESSAGES_BUTTON_PROMPT,
)
from platform_mac import macos_window as _macos_w
from platform_mac.chat_panel_scroll_capture import scroll_capture_frames_for_extraction
from shared.message_dedup import dedupe_chat_messages
from shared.sidebar_classification import unread_cap_from_badge_text
from utils.image_stitcher import save_stitched_debug, stitch_screenshots

if TYPE_CHECKING:
    from shared.vision_ai import VisionAI

class MacDriverMessages:
    pid: int
    vision_ai: "VisionAI"

    def scroll_chat_panel(self, direction: str = "down") -> None:
        assert direction in ("up", "down")
        _macos_w.activate_pid(self.pid)
        time.sleep(0.08)
        scroll_amount = 500
        clicks = scroll_amount if direction == "up" else -scroll_amount
        left, top, right, bottom = _macos_w.main_window_bounds(self.pid)
        message_panel_x = left + int((right - left) * 0.65)
        message_panel_y = top + int((bottom - top) * 0.5)
        print(f"[*] Scrolling chat panel {direction} with mouse wheel.")
        pyautogui.moveTo(message_panel_x, message_panel_y, duration=0.1)
        pyautogui.scroll(clicks)
        time.sleep(1.15)

    def click_first_unread_sidebar_row(self) -> int | None:
        rows = self.get_sidebar_rows(1)
        for row in rows:
            if row.badge_text is None:
                continue
            cap = unread_cap_from_badge_text(row.badge_text)
            print(
                f"[*] 点击带未读角标的侧栏行 {row.name!r} "
                f"(badge={row.badge_text!r} → 读取最多 {cap} 条)。"
            )
            self.click_row(row, attempt=0)
            time.sleep(0.45)
            return cap
        print("[WARN] 侧栏 Vision 结果中没有任何未读角标行。")
        return None

    def get_chat_messages(self, chat_name: str, max_messages: int | None = None) -> list[ChatMessage]:
        cap_s = f", cap={max_messages}" if max_messages else ""
        print(f"[*] Starting message extraction for '{chat_name}'{cap_s}...")
        self._activate_chat_panel_safely()
        self.click_new_messages_button()
        screenshots = scroll_capture_frames_for_extraction(self, max_messages)
        if not screenshots:
            print("[WARN] No screenshots were captured.")
            return []
        print("[*] Reversing screenshot order for processing...")
        screenshots.reverse()
        all_messages: list[ChatMessage] = []
        chunk_size = 5
        screenshot_chunks = [screenshots[i : i + chunk_size] for i in range(0, len(screenshots), chunk_size)]
        for i, chunk in enumerate(screenshot_chunks):
            print(f"--- Processing chunk {i + 1}/{len(screenshot_chunks)} ---")
            if not chunk:
                continue
            stitched_image = stitch_screenshots(images=chunk, scroll_region=None)
            if not stitched_image:
                print(f"[ERROR] Failed to stitch chunk {i + 1}.")
                continue
            debug_dir = os.environ.get("WECLAW_DEBUG_STITCH_DIR", "").strip()
            if debug_dir:
                save_stitched_debug(stitched_image, debug_dir, chat_name, i)
            response_str = self.vision_ai.query(
                CHAT_PANEL_PROMPT, stitched_image, max_tokens=16384
            )
            if not response_str:
                print(f"[ERROR] No response from AI for message extraction on chunk {i + 1}.")
                continue
            data = parse_json_object_from_model_text(response_str)
            messages_data = data.get("messages", [])
            chunk_messages = []
            for j, msg_data in enumerate(messages_data):
                if "content" not in msg_data:
                    print(f"[WARN] Chunk {i + 1}, Msg {j + 1}: Skipping message: {msg_data}")
                    continue
                chunk_messages.append(ChatMessage(**msg_data))
            if chunk_messages:
                print(f"[+] Extracted {len(chunk_messages)} messages from chunk {i + 1}.")
                all_messages.extend(chunk_messages)
            else:
                print(f"[WARN] No valid messages extracted from chunk {i + 1}.")
        out = dedupe_chat_messages(all_messages)
        if max_messages is not None and max_messages > 0 and len(out) > max_messages:
            out = out[-max_messages:]
        print(f"[*] Finished processing all chunks. Total messages: {len(out)} ({len(all_messages)} raw).")
        return out

    def _activate_chat_panel_safely(self) -> None:
        print("[*] Activating chat panel with a safe click...")
        _macos_w.activate_pid(self.pid)
        time.sleep(0.5)
        full_screenshot, wb = _macos_w.capture_window_pid_and_bounds(self.pid)
        chat_panel_x1 = int(full_screenshot.width * 0.31)
        chat_panel_y1 = 50
        chat_panel_x2 = int(full_screenshot.width * 0.95)
        chat_panel_y2 = full_screenshot.height - 50
        chat_panel_image = full_screenshot.crop((chat_panel_x1, chat_panel_y1, chat_panel_x2, chat_panel_y2))
        fw, fh = full_screenshot.size
        response_str = self.vision_ai.query(CHAT_PANEL_SAFE_CLICK_PROMPT, chat_panel_image)
        safe_click_coords = None
        if response_str:
            data = parse_json_object_from_model_text(response_str)
            bbox = data.get("bbox")
            bbox_valid = False
            if bbox and len(bbox) == 4:
                bbox_width = bbox[2] - bbox[0]
                bbox_height = bbox[3] - bbox[1]
                bbox_center_y = (bbox[1] + bbox[3]) / 2
                bbox_valid = bbox_width >= 80 and bbox_height >= 60 and bbox_center_y <= 750
            if bbox_valid:
                crop_w, crop_h = chat_panel_image.size
                cx, cy = _macos_w.vision_bbox_to_center_window_px(bbox, crop_w, crop_h)
                abs_x, abs_y = _macos_w.window_image_px_to_screen_pt(
                    chat_panel_x1 + cx,
                    chat_panel_y1 + cy,
                    fw,
                    fh,
                    wb,
                )
                safe_click_coords = (abs_x, abs_y)
                print(f"[+] AI identified safe click spot at: {safe_click_coords}")
        if not safe_click_coords:
            print("[INFO] Falling back to center of chat panel.")
            fc_x = (chat_panel_x1 + chat_panel_x2) // 2
            fc_y = (chat_panel_y1 + chat_panel_y2) // 2
            fallback_x, fallback_y = _macos_w.window_image_px_to_screen_pt(
                fc_x, fc_y, fw, fh, wb
            )
            safe_click_coords = (fallback_x, fallback_y)
        pyautogui.moveTo(safe_click_coords[0], safe_click_coords[1], duration=0.2)
        pyautogui.click()
        time.sleep(0.5)

    def get_current_chat_name(self) -> str | None:
        print("[*] Identifying current chat name from sidebar highlight...")
        full_screenshot = _macos_w.capture_window_pid(self.pid)
        if not full_screenshot:
            print("[WARN] Failed to capture window for chat name verification.")
            return None
        sidebar_width = int(full_screenshot.width * 0.3)
        sidebar_image = full_screenshot.crop((0, 0, sidebar_width, full_screenshot.height))
        response_str = self.vision_ai.query(CURRENT_CHAT_PROMPT, sidebar_image)
        if not response_str:
            print("[ERROR] Received no response from Vision AI for chat name.")
            return None
        data = parse_json_object_from_model_text(response_str)
        chat_name = data.get("chat_name")
        if chat_name:
            print(f"[+] Current chat identified as: '{chat_name}'")
            return chat_name
        print("[WARN] AI did not return a chat_name.")
        return None

    def click_new_messages_button(self) -> bool:
        print("[*] Checking for 'new messages' button...")
        full_screenshot, wb = _macos_w.capture_window_pid_and_bounds(self.pid)
        chat_panel_region = (
            int(full_screenshot.width * 0.31),
            0,
            int(full_screenshot.width * 0.95),
            full_screenshot.height,
        )
        chat_panel_screenshot = full_screenshot.crop(chat_panel_region)
        fw, fh = full_screenshot.size
        response_str = self.vision_ai.query(NEW_MESSAGES_BUTTON_PROMPT, chat_panel_screenshot)
        if not response_str:
            return False
        data = parse_json_object_from_model_text(response_str)
        bbox = data.get("bbox")
        if not bbox:
            return False
        cw, ch = chat_panel_screenshot.size
        cx_crop, cy_crop = _macos_w.vision_bbox_to_center_window_px(bbox, cw, ch)
        ix_a = chat_panel_region[0] + cx_crop
        iy_a = chat_panel_region[1] + cy_crop
        center_x, center_y = _macos_w.window_image_px_to_screen_pt(ix_a, iy_a, fw, fh, wb)
        print(f"[+] 'New messages' button found. Clicking at ({center_x}, {center_y}).")
        pyautogui.moveTo(center_x, center_y, duration=0.2)
        pyautogui.click()
        time.sleep(1)
        return True
