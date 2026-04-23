"""
Windows-specific implementation of the PlatformDriver protocol using AI Vision.
"""
import json
import os
import time
from typing import Any

import pyautogui
import win32gui

from shared.datatypes import ChatMessage, SidebarRow
from shared.platform_api import PlatformDriver
from shared.sidebar_classification import (
    parse_threads_json,
    threads_to_sidebar_rows,
)
from shared.message_time_window import (
    RECENT_WINDOW_HOURS,
    chunk_reaches_recent_cutoff,
    filter_messages_to_recent_window,
)
from shared.vision_backend import VisionBackend, create_vision_backend
from shared.vision_prompts import (
    CHAT_PANEL_PROMPT,
    CHAT_PANEL_SAFE_CLICK_PROMPT,
    CURRENT_CHAT_PROMPT,
    CURRENT_CHAT_Y_PROMPT,
    NEW_MESSAGES_BUTTON_PROMPT,
    SIDEBAR_PROMPT,
)
from platform_win.find_wechat_window import find_wechat_window as find_window
from platform_win.vision import _force_foreground_window, capture_window
from shared.message_dedup import dedupe_chat_messages
from shared.ocr_hunyuan import get_ocr_engine
from shared.vision_response_json import parse_json_object_from_model_text
from utils.image_stitcher import save_stitched_debug, stitch_screenshots


class WinDriver(PlatformDriver):
    def __init__(self, vision_backend: VisionBackend | None = None):
        self.hwnd: int = 0
        self.vision_ai: VisionBackend = vision_backend or create_vision_backend("openrouter")

    def find_wechat_window(self, app_name: str = "微信") -> int:
        """Finds the WeChat window and stores its handle."""
        self.hwnd = find_window(app_name=app_name)
        if not self.hwnd:
            raise RuntimeError(
                f"WeChat window '{app_name}' not found. Please ensure it is running."
            )
        print(f"[+] WeChat window '{app_name}' found with HWND: {self.hwnd}")
        return self.hwnd

    def _get_precise_row_coords(self, row: SidebarRow) -> tuple[int, int] | None:
        """
        Uses PaddleOCR on the sidebar crop to find the pixel-exact center of the
        target chat row. No VLM call needed — OCR gives pixel bboxes directly.
        """
        chat_name = row.name
        print(f"[*] Getting precise coordinates for '{chat_name}' using OCR...")
        full_screenshot = capture_window(self.hwnd)
        if not full_screenshot:
            print(f"[WARN] Failed to capture window for precise coordinate detection.")
            return None

        window_rect = win32gui.GetWindowRect(self.hwnd)
        window_left, window_top, _, _ = window_rect

        sidebar_width = int(full_screenshot.width * 0.3)
        sidebar_image = full_screenshot.crop((0, 0, sidebar_width, full_screenshot.height))

        ocr_engine = get_ocr_engine()
        raw_lines = ocr_engine.recognize(sidebar_image)
        hit = ocr_engine.match_target(raw_lines, chat_name)

        if hit is None:
            print(f"[ERROR] OCR could not locate '{chat_name}' in sidebar.")
            return None

        abs_x = window_left + hit.center_x
        abs_y = window_top + hit.center_y
        print(f"[+] Precise coordinates for '{chat_name}' found via OCR: ({abs_x}, {abs_y})")
        return (abs_x, abs_y)

    def get_sidebar_rows(self, window: Any) -> list[SidebarRow]:
        """Gets all visible rows in the sidebar using PaddleOCR (names) + VLM (semantics)."""
        hwnd = window
        full_screenshot = capture_window(hwnd)
        if not full_screenshot:
            print("[WARN] Failed to capture window for sidebar row detection.")
            return []

        window_left, window_top, _, _ = win32gui.GetWindowRect(hwnd)

        sidebar_width = int(full_screenshot.width * 0.3)
        sidebar_crop_box = (0, 0, sidebar_width, full_screenshot.height)
        sidebar_image = full_screenshot.crop(sidebar_crop_box)

        img_width, img_height = sidebar_image.size

        # --- Step 1: PaddleOCR — precise Chinese text + pixel bboxes ---
        ocr_engine = get_ocr_engine()
        raw_lines = ocr_engine.recognize(sidebar_image)
        if not raw_lines:
            print("[WARN] PaddleOCR returned no text; falling back to VLM-only mode.")
            raw_lines = []

        if raw_lines:
            rows: list[SidebarRow] = []
            for ocr_line in raw_lines:
                ox1, oy1, ox2, oy2 = ocr_line.bbox
                row_half = max((oy2 - oy1) // 2, 10)
                cy = (oy1 + oy2) // 2
                y1 = max(0, cy - row_half)
                y2 = min(img_height, cy + row_half)
                box = (
                    window_left,
                    window_top + y1,
                    window_left + sidebar_width,
                    window_top + y2,
                )
                rows.append(
                    SidebarRow(
                        name=ocr_line.text,
                        last_message=None,
                        badge_text=None,
                        bbox=box,
                        is_group=True,
                    )
                )
            print(f"[+] OCR identified {len(rows)} raw sidebar rows (no merge, all marked as group).")
            return rows

        # Build OCR hint list for VLM to reduce hallucination
        ocr_name_hints = [ln.text for ln in raw_lines]

        # --- Step 2: VLM — is_group / unread / y_norm per row ---
        hint_clause = ""
        if ocr_name_hints:
            names_csv = ", ".join(f'"{n}"' for n in ocr_name_hints)
            hint_clause = (
                f"\nOCR text fragments top-to-bottom (may mix titles, previews, or UI noise): [{names_csv}]. "
                "Emit one JSON thread per visible session row. "
                "Each \"name\" MUST be the real session title shown on that row (left column), "
                "never the last-message preview line below it. "
                "If OCR listed a preview instead of the title, use the title text you see in the image."
            )

        augmented_prompt = SIDEBAR_PROMPT + hint_clause

        print(f"[DEBUG] OCR raw lines: {len(raw_lines)} rows, sending as hints to VLM.")

        print("[*] Querying Vision AI to analyze sidebar...")
        response_str = self.vision_ai.query(augmented_prompt, sidebar_image)

        vlm_threads: list[dict] = []
        if response_str:
            try:
                vlm_threads = parse_threads_json(response_str)
            except (json.JSONDecodeError, ValueError, TypeError) as e:
                print(f"[WARN] Failed to parse sidebar VLM response: {e}. Using OCR names only.")
        else:
            print("[WARN] No VLM response for sidebar; using OCR names with defaults.")

        # --- Step 3: Merge OCR rows with VLM semantics by name (primary) then y ---
        # VLM is instructed to use exact OCR names, so name-match is reliable.
        # Fall back to nearest-y only for rows the VLM named slightly differently.
        def _vlm_y_px(thread: dict) -> int:
            y_norm = float(thread.get("y", 0))
            return int(y_norm / 1000.0 * img_height)

        vlm_by_name: dict[str, dict] = {t.get("name", ""): t for t in vlm_threads}

        def _best_vlm_thread(ocr_text: str, ocr_cy: int) -> dict:
            # 1. Exact name match
            if ocr_text in vlm_by_name:
                return vlm_by_name[ocr_text]
            # 2. Nearest-y fallback
            if vlm_threads:
                return min(vlm_threads, key=lambda t: abs(_vlm_y_px(t) - ocr_cy))
            return {}

        rows: list[SidebarRow] = []

        if raw_lines:
            for ocr_line in raw_lines:
                ocr_cy = ocr_line.center_y
                best_thread = _best_vlm_thread(ocr_line.text, ocr_cy)

                is_group = bool(best_thread.get("is_group", False)) if best_thread else False
                unread = bool(best_thread.get("unread", False)) if best_thread else False
                unread_badge_raw = best_thread.get("unread_badge") if best_thread else None

                if unread:
                    badge = str(unread_badge_raw).strip() if unread_badge_raw else "1"
                else:
                    badge = None

                # Pixel bbox of this OCR row → absolute screen coords
                ox1, oy1, ox2, oy2 = ocr_line.bbox
                # Expand row height to be at least 20px tall (for click accuracy)
                row_half = max((oy2 - oy1) // 2, 10)
                cy = (oy1 + oy2) // 2
                y1 = max(0, cy - row_half)
                y2 = min(img_height, cy + row_half)
                box = (
                    window_left,
                    window_top + y1,
                    window_left + sidebar_width,
                    window_top + y2,
                )
                rows.append(
                    SidebarRow(
                        name=ocr_line.text,
                        last_message=None,
                        badge_text=badge,
                        bbox=box,
                        is_group=is_group,
                    )
                )
        else:
            # Full fallback: VLM only (original behaviour)
            rows = threads_to_sidebar_rows(
                vlm_threads, img_width, img_height, window_left, window_top
            )

        print(f"[+] AI identified {len(rows)} sidebar rows.")
        return rows

    def ensure_permissions(self) -> None:
        raise NotImplementedError

    def scroll_sidebar(self, window: Any, direction: str) -> None:
        """Scrolls the sidebar up or down by simulating mouse wheel movement."""
        hwnd = window
        if not self.hwnd:
            raise RuntimeError("WeChat window not found. Call find_wechat_window() first.")

        _force_foreground_window(hwnd)

        scroll_amount = 500
        if direction == "up":
            clicks = scroll_amount
        elif direction == "down":
            clicks = -scroll_amount
        else:
            raise ValueError(f"Invalid scroll direction: '{direction}'. Must be 'up' or 'down'.")

        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        sidebar_x = left + int((right - left) * 0.15)
        sidebar_y = top + int((bottom - top) * 0.5)

        print(f"[*] Scrolling sidebar {direction}...", end=" ")
        pyautogui.moveTo(sidebar_x, sidebar_y, duration=0.1)
        pyautogui.scroll(clicks)
        print("Done.")

    def get_row_name(self, row: Any) -> str:
        """Extracts the chat name from a SidebarRow."""
        if not isinstance(row, SidebarRow):
            return ""
        return row.name

    def get_row_badge_text(self, row: Any) -> str | None:
        """Extracts the badge text (e.g., unread count) from a SidebarRow."""
        if not isinstance(row, SidebarRow):
            return None
        return row.badge_text

    def scroll_chat_panel(self, direction: str = "down") -> None:
        """Scrolls the chat panel via mouse wheel at the message area (same as scroll_messages)."""
        if not self.hwnd:
            raise RuntimeError("WeChat window not found. Call find_wechat_window() first.")
        if direction == "up":
            clicks = 500
        elif direction == "down":
            clicks = -500
        else:
            raise ValueError(f"Invalid scroll direction: '{direction}'. Must be 'up' or 'down'.")
        _force_foreground_window(self.hwnd)
        left, top, right, bottom = win32gui.GetWindowRect(self.hwnd)
        message_panel_x = left + int((right - left) * 0.65)
        message_panel_y = top + int((bottom - top) * 0.5)
        print(f"[*] Scrolling chat panel {direction} with mouse wheel.")
        pyautogui.moveTo(message_panel_x, message_panel_y, duration=0.1)
        pyautogui.scroll(clicks)
        time.sleep(1.0)

    def get_chat_messages(self, chat_name: str) -> list[ChatMessage]:
        """
        Orchestrates the process of scrolling, capturing, stitching, and extracting
        chat messages from the current chat.
        This version scrolls UP, captures, and then reverses the sequence for stitching.
        """
        print(f"[*] Starting message extraction for '{chat_name}'...")

        self._activate_chat_panel_safely()

        self.click_new_messages_button()

        screenshots = []
        for i in range(10):
            self.scroll_chat_panel(direction="up")
            screenshot = capture_window(self.hwnd)
            if screenshot:
                screenshots.append(screenshot)

        if not screenshots:
            print("[WARN] No screenshots were captured.")
            return []

        print("[*] Reversing screenshot order for processing...")
        screenshots.reverse()

        all_messages = []
        chunk_size = 5
        screenshot_chunks = [screenshots[i:i + chunk_size] for i in range(0, len(screenshots), chunk_size)]
        chunk_results = []

        print(f"[*] Processing {len(screenshots)} screenshots in {len(screenshot_chunks)} chunks of size {chunk_size}.")

        for idx in range(len(screenshot_chunks) - 1, -1, -1):
            chunk = screenshot_chunks[idx]
            print(f"--- Processing chunk {idx+1}/{len(screenshot_chunks)} ---")
            if not chunk:
                continue

            stitched_image = stitch_screenshots(images=chunk, scroll_region=None)

            if not stitched_image:
                print(f"[ERROR] Failed to stitch chunk {idx+1}.")
                continue

            debug_dir = os.environ.get("WECLAW_DEBUG_STITCH_DIR", "").strip()
            if debug_dir:
                save_stitched_debug(stitched_image, debug_dir, chat_name, idx)

            try:
                response_str = self.vision_ai.query(
                    CHAT_PANEL_PROMPT, stitched_image, max_tokens=16384
                )
            except Exception as e:
                print(f"[ERROR] Vision AI query for chunk {idx+1} failed: {e}")
                continue

            if not response_str:
                print(f"[ERROR] No response from AI for message extraction on chunk {idx+1}.")
                continue

            try:
                data = parse_json_object_from_model_text(response_str)
                messages_data = data.get("messages", [])
                chunk_messages = []

                for j, msg_data in enumerate(messages_data):
                    if "content" not in msg_data:
                        print(f"[WARN] Chunk {idx+1}, Msg {j+1}: Skipping message due to missing 'content': {msg_data}")
                        continue

                    try:
                        chunk_messages.append(ChatMessage(**msg_data))
                    except TypeError as e:
                        print(f"[WARN] Chunk {idx+1}, Msg {j+1}: Skipping message during creation: {msg_data}. Error: {e}")

                if chunk_messages:
                    filtered_chunk = filter_messages_to_recent_window(
                        chunk_messages,
                        hours=RECENT_WINDOW_HOURS,
                    )
                    print(f"[+] Extracted {len(chunk_messages)} messages from chunk {idx+1}.")
                    if filtered_chunk:
                        chunk_results.append((idx, filtered_chunk))
                    if chunk_reaches_recent_cutoff(
                        chunk_messages,
                        hours=RECENT_WINDOW_HOURS,
                    ):
                        print(
                            f"[*] Chunk {idx+1} reached the {RECENT_WINDOW_HOURS}-hour cutoff. "
                            "Skipping older chunks."
                        )
                        break
                else:
                    print(f"[WARN] No valid messages extracted from chunk {idx+1}.")

            except Exception as e:
                print(f"[ERROR] Failed to parse messages from AI response for chunk {idx+1}: {e}")
                print(f"Raw response was: {response_str}")
                continue

        chunk_results.sort(key=lambda item: item[0])
        for _, chunk_messages in chunk_results:
            all_messages.extend(chunk_messages)
        out = dedupe_chat_messages(all_messages)
        print(f"[*] Finished processing all chunks. Total messages: {len(out)} ({len(all_messages)} raw).")
        return out

    def _activate_chat_panel_safely(self) -> None:
        """Finds a safe spot in the chat panel to click to activate the window."""
        print("[*] Activating chat panel with a safe click...")
        _force_foreground_window(self.hwnd)
        time.sleep(0.5) # Wait for window to be focused

        full_screenshot = capture_window(self.hwnd)
        if not full_screenshot:
            print("[WARN] Failed to capture window for safe click.")
            return

        window_rect = win32gui.GetWindowRect(self.hwnd)
        window_left, window_top, _, _ = window_rect

        # Define and crop to the chat panel region
        chat_panel_x1 = int(full_screenshot.width * 0.31)
        chat_panel_y1 = 50 # Avoid header
        chat_panel_x2 = int(full_screenshot.width * 0.95)
        chat_panel_y2 = full_screenshot.height - 50 # Avoid input area
        chat_panel_crop_box = (chat_panel_x1, chat_panel_y1, chat_panel_x2, chat_panel_y2)
        chat_panel_image = full_screenshot.crop(chat_panel_crop_box)

        # Query AI for a safe spot
        response_str = self.vision_ai.query(CHAT_PANEL_SAFE_CLICK_PROMPT, chat_panel_image)

        safe_click_coords = None
        bbox = None
        bbox_width = None
        bbox_height = None
        bbox_center_y = None
        bbox_valid = False
        if response_str:
            try:
                data = parse_json_object_from_model_text(response_str)
                bbox = data.get("bbox")
                if bbox and len(bbox) == 4:
                    bbox_width = bbox[2] - bbox[0]
                    bbox_height = bbox[3] - bbox[1]
                    bbox_center_y = (bbox[1] + bbox[3]) / 2
                    bbox_valid = (
                        bbox_width >= 80
                        and bbox_height >= 60
                        and bbox_center_y <= 750
                    )
                if bbox_valid:
                    # The AI is assumed to return coordinates in a 1000x1000 space
                    img_width, img_height = chat_panel_image.size
                    scaled_x1 = int(bbox[0] / 1000 * img_width)
                    scaled_y1 = int(bbox[1] / 1000 * img_height)
                    scaled_x2 = int(bbox[2] / 1000 * img_width)
                    scaled_y2 = int(bbox[3] / 1000 * img_height)

                    # Calculate center and convert to absolute screen coordinates
                    center_x = (scaled_x1 + scaled_x2) // 2
                    center_y = (scaled_y1 + scaled_y2) // 2
                    abs_x = window_left + chat_panel_x1 + center_x
                    abs_y = window_top + chat_panel_y1 + center_y
                    safe_click_coords = (abs_x, abs_y)
                    print(f"[+] AI identified safe click spot at: {safe_click_coords}")
                elif bbox:
                    print(f"[WARN] AI returned an unsafe click bbox: {bbox}")
            except Exception as e:
                print(f"[WARN] Could not parse safe click response from AI: {e}. Falling back to default.")

        # If AI fails or doesn't provide a spot, fall back to clicking the center
        if not safe_click_coords:
            print("[INFO] AI did not provide a safe click spot. Falling back to center of chat panel.")
            fallback_x = window_left + (chat_panel_x1 + chat_panel_x2) // 2
            fallback_y = window_top + (chat_panel_y1 + chat_panel_y2) // 2
            safe_click_coords = (fallback_x, fallback_y)

        pyautogui.moveTo(safe_click_coords[0], safe_click_coords[1], duration=0.2)
        pyautogui.click()
        time.sleep(0.5)

    def get_current_chat_name(self) -> str | None:
        """Captures the sidebar and identifies the currently selected (highlighted) chat.

        Strategy:
        1. VLM directly returns the highlighted row's chat_name.
        2. Fallback: VLM returns highlighted y, then map to nearest OCR row.
        """
        print("[*] Identifying current chat name from sidebar highlight...")
        full_screenshot = capture_window(self.hwnd)
        if not full_screenshot:
            print("[WARN] Failed to capture window for chat name verification.")
            return None

        sidebar_width = int(full_screenshot.width * 0.3)
        sidebar_image = full_screenshot.crop((0, 0, sidebar_width, full_screenshot.height))
        img_height = sidebar_image.height

        # Step 1: ask VLM for highlighted row name directly (more robust than OCR y-mapping).
        direct_resp = self.vision_ai.query(CURRENT_CHAT_PROMPT, sidebar_image)
        if direct_resp:
            try:
                direct_data = parse_json_object_from_model_text(direct_resp)
                direct_name = str(direct_data.get("chat_name", "") or "").strip()
                if direct_name and direct_name.lower() not in ("null", "none"):
                    print(f"[+] Current chat identified by VLM name: '{direct_name}'")
                    return direct_name
            except Exception as e:
                print(f"[WARN] Failed direct current chat parse, fallback to y+OCR. Error: {e}")

        # Step 2 (fallback): OCR all text lines
        ocr_engine = get_ocr_engine()
        raw_lines = ocr_engine.recognize(sidebar_image)

        # Step 3 (fallback): VLM returns the y of highlighted row
        response_str = self.vision_ai.query(CURRENT_CHAT_Y_PROMPT, sidebar_image)

        if not response_str:
            print("[ERROR] No response from Vision AI for current chat identification.")
            return None

        try:
            data = parse_json_object_from_model_text(response_str)
            y_norm = data.get("y")
            if y_norm is None:
                print("[WARN] VLM did not identify a highlighted row.")
                return None

            y_px = int(float(y_norm) / 1000.0 * img_height)

            # Step 3: Find nearest OCR line
            lines_to_search = raw_lines
            if not lines_to_search:
                print("[WARN] OCR returned no lines; cannot map highlighted row.")
                return None

            nearest = min(lines_to_search, key=lambda ln: abs(ln.center_y - y_px))
            chat_name = nearest.text
            print(f"[+] Current chat identified as: '{chat_name}'")
            return chat_name

        except Exception as e:
            print(f"[ERROR] Failed to parse current chat response. Exception: {e}")
            print(f"Raw response was: {response_str}")
            return None

    def _get_chat_panel_region(self) -> tuple[int, int, int, int]:
        """Calculates the bounding box of the chat panel region."""
        full_screenshot = capture_window(self.hwnd)
        if not full_screenshot:
            return (0, 0, 0, 0)

        chat_panel_x1 = int(full_screenshot.width * 0.31)
        chat_panel_y1 = 0 
        chat_panel_x2 = int(full_screenshot.width * 0.95)
        chat_panel_y2 = full_screenshot.height

        return (chat_panel_x1, chat_panel_y1, chat_panel_x2, chat_panel_y2)

    def click_new_messages_button(self) -> bool:
        """
        Checks for a "new messages" button and clicks it if found.
        Returns True if a button was clicked, False otherwise.
        """
        print("[*] Checking for 'new messages' button...")
        full_screenshot = capture_window(self.hwnd)
        if not full_screenshot:
            print("[WARN] Failed to capture window for new messages button check.")
            return False

        window_rect = win32gui.GetWindowRect(self.hwnd)
        window_left, window_top, _, _ = window_rect

        chat_panel_region = (
            int(full_screenshot.width * 0.31),
            0,
            int(full_screenshot.width * 0.95),
            full_screenshot.height
        )
        chat_panel_screenshot = full_screenshot.crop(chat_panel_region)

        response_str = self.vision_ai.query(NEW_MESSAGES_BUTTON_PROMPT, chat_panel_screenshot)

        if not response_str:
            print("[DEBUG] No response from AI for new messages button check.")
            return False

        try:
            data = parse_json_object_from_model_text(response_str)
            bbox = data.get("bbox")

            if not bbox:
                print("[DEBUG] No 'new messages' button found by AI.")
                return False

            img_w, img_h = chat_panel_screenshot.size
            px_x1 = int(bbox[0] / 1000 * img_w)
            px_y1 = int(bbox[1] / 1000 * img_h)
            px_x2 = int(bbox[2] / 1000 * img_w)
            px_y2 = int(bbox[3] / 1000 * img_h)

            abs_x1 = window_left + chat_panel_region[0] + px_x1
            abs_y1 = window_top + chat_panel_region[1] + px_y1
            abs_x2 = window_left + chat_panel_region[0] + px_x2
            abs_y2 = window_top + chat_panel_region[1] + px_y2

            center_x = (abs_x1 + abs_x2) // 2
            center_y = (abs_y1 + abs_y2) // 2

            print(f"[+] 'New messages' button found. Clicking at ({center_x}, {center_y}).")
            pyautogui.moveTo(center_x, center_y, duration=0.2)
            pyautogui.click()
            time.sleep(1) 
            return True

        except Exception as e:
            print(f"[ERROR] Failed to process AI response for new messages button: {e}")
            print(f"Raw response was: {response_str}")
            return False

    def click_row(self, row: SidebarRow, attempt: int = 0) -> None:
        """
        Clicks on a given SidebarRow element.
        On subsequent attempts, it can apply a vertical offset.
        """
        if not isinstance(row, SidebarRow):
            print(f"[WARN] click_row called with invalid type: {type(row)}")
            return

        center_x: int | None = None
        center_y: int | None = None

        # Fast path: click directly from SidebarRow bbox (already absolute screen coords).
        if row.bbox and len(row.bbox) == 4:
            x1, y1, x2, y2 = row.bbox
            center_x = (int(x1) + int(x2)) // 2
            center_y = (int(y1) + int(y2)) // 2
        else:
            coords = self._get_precise_row_coords(row)
            if not coords:
                print(f"[ERROR] Could not get click coordinates for '{row.name}'. Aborting click.")
                return
            center_x, center_y = coords

        y_offset = 0
        if attempt > 0:
            y_offset = -10 * attempt 

        adjusted_y = center_y + y_offset

        print(f"[*] Preparing to click on row '{row.name}'. Attempt: {attempt + 1}, Coords: ({center_x}, {adjusted_y})")

        pyautogui.moveTo(center_x, adjusted_y, duration=0.5)

        pyautogui.click()
        print("[+] Click action sent.")

    def get_message_elements(self, window: Any) -> list:
        """This function is obsolete in the new AI-driven driver."""
        print("[WARN] get_message_elements is not implemented in the AI driver and will be removed.")
        return []

    def scroll_messages(self, window: Any, direction: str) -> None:
        """Scrolls the message panel up or down."""
        hwnd = window
        if not self.hwnd:
            raise RuntimeError("WeChat window not found. Call find_wechat_window() first.")

        _force_foreground_window(hwnd)

        scroll_amount = 500
        if direction == "up":
            clicks = scroll_amount
        elif direction == "down":
            clicks = -scroll_amount
        else:
            raise ValueError(f"Invalid scroll direction: '{direction}'. Must be 'up' or 'down'.")

        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        message_panel_x = left + int((right - left) * 0.65)
        message_panel_y = top + int((bottom - top) * 0.5)

        print(f"[*] Scrolling message panel {direction}...", end=" ")
        pyautogui.moveTo(message_panel_x, message_panel_y, duration=0.1)
        pyautogui.scroll(clicks)
        print("Done.")


