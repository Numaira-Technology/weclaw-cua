"""macOS：聊天区消息提取、侧栏当前会话名、新消息按钮。"""

import time
from typing import TYPE_CHECKING

import pyautogui

from shared.datatypes import ChatMessage
from shared.vision_image_codec import log_vision_timing
from shared.message_time_window import (
    RECENT_WINDOW_HOURS,
    chunk_reaches_recent_cutoff,
    filter_messages_to_recent_window,
)
from shared.vision_response_json import parse_json_object_from_model_text
from shared.vision_prompts import (
    CHAT_PANEL_PROMPT, CHAT_PANEL_SAFE_CLICK_PROMPT, CURRENT_CHAT_PROMPT,
    CURRENT_CHAT_Y_PROMPT, NEW_MESSAGES_BUTTON_PROMPT,
)
from shared.ocr_hunyuan import get_ocr_engine
from platform_mac import macos_window as _macos_w
from platform_mac.chat_panel_scroll_capture import scroll_capture_frames_for_extraction
from shared.message_dedup import dedupe_chat_messages
from shared.sidebar_classification import unread_cap_from_badge_text
from utils.chat_stitch_debug import new_chat_stitch_session_basename, save_chat_stitch_for_vlm
from utils.image_stitcher import stitch_screenshots

if TYPE_CHECKING:
    from shared.vision_backend import VisionBackend

class MacDriverMessages:
    pid: int
    vision_ai: "VisionBackend"

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
        getter = getattr(self, "get_fast_sidebar_rows", None)
        rows = getter(1) if getter is not None else self.get_sidebar_rows(1)
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

    def get_chat_messages(
        self,
        chat_name: str,
        max_messages: int | None = None,
        max_scrolls: int | None = None,
        skip_navigation_vlm: bool = False,
    ) -> list[ChatMessage]:
        cap_s = f", cap={max_messages}" if max_messages else ""
        print(f"[*] Starting message extraction for '{chat_name}'{cap_s}...")
        if skip_navigation_vlm:
            self._activate_chat_panel_by_center()
        else:
            self._activate_chat_panel_safely()
            self.click_new_messages_button()
        screenshots = scroll_capture_frames_for_extraction(
            self,
            max_messages,
            max_scrolls=max_scrolls,
        )
        if not screenshots:
            print("[WARN] No screenshots were captured.")
            return []
        print("[*] Reversing screenshot order for processing...")
        screenshots.reverse()
        all_messages: list[ChatMessage] = []
        chunk_size = 25
        screenshot_chunks = [screenshots[i : i + chunk_size] for i in range(0, len(screenshots), chunk_size)]
        chunk_results: list[tuple[int, list[ChatMessage]]] = []
        stitch_session = new_chat_stitch_session_basename()
        for idx in range(len(screenshot_chunks) - 1, -1, -1):
            chunk = screenshot_chunks[idx]
            print(f"--- Processing chunk {idx + 1}/{len(screenshot_chunks)} ---")
            if not chunk:
                continue
            stitch_started = time.perf_counter()
            stitched_image = stitch_screenshots(images=chunk, scroll_region=None)
            stitch_seconds = time.perf_counter() - stitch_started
            if not stitched_image:
                print(f"[ERROR] Failed to stitch chunk {idx + 1}.")
                continue
            log_vision_timing(
                "mac_driver_messages",
                "stitch",
                chat=chat_name,
                chunk_index=idx + 1,
                chunk_total=len(screenshot_chunks),
                frame_count=len(chunk),
                width=stitched_image.width,
                height=stitched_image.height,
                stitch_ms=round(stitch_seconds * 1000, 1),
            )
            save_chat_stitch_for_vlm(stitch_session, chat_name, idx, stitched_image)
            try:
                response_str = self.vision_ai.query(
                    CHAT_PANEL_PROMPT, stitched_image, max_tokens=16384
                )
            except Exception as e:
                print(f"[ERROR] Vision AI query for chunk {idx + 1} failed: {e}")
                continue
            if not response_str:
                print(f"[ERROR] No response from AI for message extraction on chunk {idx + 1}.")
                continue
            try:
                data = parse_json_object_from_model_text(response_str)
                messages_data = data.get("messages", [])
            except Exception as e:
                print(f"[ERROR] Failed to parse messages from AI response for chunk {idx + 1}: {e}")
                print(f"Raw response was: {response_str}")
                continue
            chunk_messages = []
            for j, msg_data in enumerate(messages_data):
                if "content" not in msg_data:
                    print(f"[WARN] Chunk {idx + 1}, Msg {j + 1}: Skipping message: {msg_data}")
                    continue
                chunk_messages.append(ChatMessage(**msg_data))
            if chunk_messages:
                filtered_chunk = filter_messages_to_recent_window(
                    chunk_messages,
                    hours=RECENT_WINDOW_HOURS,
                )
                print(f"[+] Extracted {len(chunk_messages)} messages from chunk {idx + 1}.")
                if filtered_chunk:
                    chunk_results.append((idx, filtered_chunk))
                if chunk_reaches_recent_cutoff(
                    chunk_messages,
                    hours=RECENT_WINDOW_HOURS,
                ):
                    print(
                        f"[*] Chunk {idx + 1} reached the {RECENT_WINDOW_HOURS}-hour cutoff. "
                        "Skipping older chunks."
                    )
                    break
            else:
                print(f"[WARN] No valid messages extracted from chunk {idx + 1}.")
        chunk_results.sort(key=lambda item: item[0])
        for _, chunk_messages in chunk_results:
            all_messages.extend(chunk_messages)
        out = dedupe_chat_messages(all_messages)
        if max_messages is not None and max_messages > 0 and len(out) > max_messages:
            out = out[-max_messages:]
        print(f"[*] Finished processing all chunks. Total messages: {len(out)} ({len(all_messages)} raw).")
        return out

    def _activate_chat_panel_by_center(self) -> None:
        print("[*] Activating chat panel at deterministic center.")
        _macos_w.activate_pid(self.pid)
        time.sleep(0.2)
        full_screenshot, wb = _macos_w.capture_window_pid_and_bounds(self.pid)
        fw, fh = full_screenshot.size
        chat_panel_x1 = int(full_screenshot.width * 0.31)
        chat_panel_y1 = 50
        chat_panel_x2 = int(full_screenshot.width * 0.95)
        chat_panel_y2 = full_screenshot.height - 50
        fc_x = (chat_panel_x1 + chat_panel_x2) // 2
        fc_y = (chat_panel_y1 + chat_panel_y2) // 2
        click_x, click_y = _macos_w.window_image_px_to_screen_pt(
            fc_x,
            fc_y,
            fw,
            fh,
            wb,
        )
        pyautogui.moveTo(click_x, click_y, duration=0.1)
        pyautogui.click()
        time.sleep(0.3)

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
        """VLM direct name → OCR + VLM y-mapping fallback."""
        print("[*] Identifying current chat name from sidebar highlight...")
        full_screenshot = _macos_w.capture_window_pid(self.pid)
        if not full_screenshot:
            print("[WARN] Failed to capture window for chat name verification.")
            return None
        sidebar_width = int(full_screenshot.width * 0.3)
        sidebar_image = full_screenshot.crop((0, 0, sidebar_width, full_screenshot.height))
        img_height = sidebar_image.height

        direct_resp = self.vision_ai.query(CURRENT_CHAT_PROMPT, sidebar_image)
        if direct_resp:
            data = parse_json_object_from_model_text(direct_resp)
            direct_name = str(data.get("chat_name", "") or "").strip()
            if direct_name and direct_name.lower() not in ("null", "none"):
                print(f"[+] Current chat identified by VLM name: '{direct_name}'")
                return direct_name

        try:
            ocr_engine = get_ocr_engine()
            raw_lines = ocr_engine.recognize(sidebar_image)
        except Exception as e:
            print(f"[WARN] HunyuanOCR unavailable ({type(e).__name__}); skipping OCR fallback for chat name.")
            return None

        response_str = self.vision_ai.query(CURRENT_CHAT_Y_PROMPT, sidebar_image)
        if not response_str:
            print("[ERROR] No response from Vision AI for current chat y-coord.")
            return None

        data = parse_json_object_from_model_text(response_str)
        y_norm = data.get("y")
        if y_norm is None:
            print("[WARN] VLM did not identify a highlighted row.")
            return None

        y_px = int(float(y_norm) / 1000.0 * img_height)

        if not raw_lines:
            print("[WARN] OCR returned no lines; cannot map highlighted row.")
            return None

        nearest = min(raw_lines, key=lambda ln: abs(ln.center_y - y_px))
        chat_name = nearest.text
        print(f"[+] Current chat identified via OCR+y mapping: '{chat_name}'")
        return chat_name

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
