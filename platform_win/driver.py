"""
Windows-specific implementation of the PlatformDriver protocol using AI Vision.
"""
import json
import os
import re
import time
from typing import Any

import pyautogui  # type: ignore[import-untyped]
import win32gui  # type: ignore[import-untyped]

from shared.datatypes import ChatMessage, SidebarRow
from shared.sidebar_ui_chrome import is_sidebar_ui_chrome_label
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
    CURRENT_CHAT_Y_PROMPT,
    NEW_MESSAGES_BUTTON_PROMPT,
    SIDEBAR_CHAT_NAMES_PROMPT,
    SIDEBAR_PROMPT,
)
from shared.vision_image_codec import log_vision_timing
from platform_win.find_wechat_window import find_wechat_window as find_window
from platform_win.sidebar_ocr_debug import (
    make_row_debug_entry,
    new_sidebar_debug_prefix,
    print_ocr_lines,
    save_sidebar_crop,
    write_sidebar_debug,
)
from platform_win.vision import _force_foreground_window, capture_window
from shared.message_dedup import dedupe_chat_messages
from shared.ocr_paddle import get_ocr_engine
from shared.vision_response_json import parse_json_object_from_model_text
from utils.chat_stitch_debug import (
    new_chat_stitch_session_basename,
    save_chat_frame_before_stitch,
    save_chat_stitch_for_vlm,
)
from utils.image_stitcher import CropRegion, stitch_screenshots


def _clean_header_title(text: str) -> str:
    out = re.sub(r"\s+", " ", str(text or "")).strip()
    out = re.sub(r"[（(]\d+[）)]$", "", out).strip()
    return out.strip(" \t、，。：；\"'")


def _is_plausible_header_title(text: str) -> bool:
    title = str(text or "").strip()
    if len(title) < 2:
        return False
    if title.isdigit():
        return False
    junk = sum(1 for ch in title if ch in "+0123456789⑦⑧⑨⑩①②③④⑤⑥⑪⑫⑬⑭⑮ \t·.。:：")
    return junk < len(title) * 0.5


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
        Uses RapidOCR on the sidebar crop to find the pixel-exact center of the
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

    def _ocr_sidebar_rows_from_image(
        self,
        sidebar_image,
        window_left: int,
        window_top: int,
        sidebar_width: int,
        vlm_threads: list[dict] | None = None,
    ) -> tuple[list[SidebarRow], list[Any], list[dict[str, Any]]]:
        ocr_engine = get_ocr_engine()
        raw_lines = ocr_engine.recognize(sidebar_image)
        img_height = sidebar_image.height
        threads = vlm_threads or []

        def _vlm_y_px(thread: dict) -> int:
            y_norm = float(thread.get("y", 0))
            return int(y_norm / 1000.0 * img_height)

        vlm_by_name: dict[str, dict] = {t.get("name", ""): t for t in threads}

        def _best_vlm_thread(ocr_text: str, ocr_cy: int) -> dict:
            if ocr_text in vlm_by_name:
                return vlm_by_name[ocr_text]
            if threads:
                return min(threads, key=lambda t: abs(_vlm_y_px(t) - ocr_cy))
            return {}

        rows: list[SidebarRow] = []
        row_debug_entries: list[dict[str, Any]] = []
        for ocr_line in raw_lines:
            if is_sidebar_ui_chrome_label(ocr_line.text):
                continue
            best_thread = _best_vlm_thread(ocr_line.text, ocr_line.center_y)
            is_group = bool(best_thread.get("is_group", False)) if best_thread else False
            unread = bool(best_thread.get("unread", False)) if best_thread else False
            unread_badge_raw = best_thread.get("unread_badge") if best_thread else None
            badge = str(unread_badge_raw).strip() if unread and unread_badge_raw else None
            if unread and not badge:
                badge = "1"
            _, oy1, _, oy2 = ocr_line.bbox
            row_half = max((oy2 - oy1) // 2, 10)
            cy = (oy1 + oy2) // 2
            y1 = max(0, cy - row_half)
            y2 = min(img_height, cy + row_half)
            row = SidebarRow(
                name=ocr_line.text,
                last_message=None,
                badge_text=badge,
                bbox=(
                    window_left,
                    window_top + y1,
                    window_left + sidebar_width,
                    window_top + y2,
                ),
                is_group=is_group,
            )
            rows.append(row)
            row_debug_entries.append(make_row_debug_entry(ocr_line, row, best_thread))
        return rows, raw_lines, row_debug_entries

    def get_fast_sidebar_rows(self, window: Any) -> list[SidebarRow]:
        """Return visible sidebar rows using RapidOCR only."""
        hwnd = window
        full_screenshot = capture_window(hwnd)
        if not full_screenshot:
            print("[WARN] Failed to capture window for fast sidebar row detection.")
            return []
        window_left, window_top, _, _ = win32gui.GetWindowRect(hwnd)
        sidebar_width = int(full_screenshot.width * 0.3)
        sidebar_image = full_screenshot.crop((0, 0, sidebar_width, full_screenshot.height))
        rows, raw_lines, row_debug_entries = self._ocr_sidebar_rows_from_image(
            sidebar_image,
            window_left,
            window_top,
            sidebar_width,
        )
        debug_prefix = new_sidebar_debug_prefix()
        save_sidebar_crop(debug_prefix, sidebar_image)
        print_ocr_lines("Fast OCR raw lines", raw_lines)
        print_ocr_lines("Fast OCR rows (no merge)", raw_lines)
        write_sidebar_debug(debug_prefix, raw_lines, [], row_debug_entries)
        print(f"[+] Fast OCR identified {len(rows)} sidebar rows.")
        return rows

    def capture_sidebar_chat_names(
        self,
        window: Any,
        max_scrolls: int,
    ) -> list[str]:
        """Capture a stitched sidebar strip and return chat names from first-line text."""
        assert max_scrolls >= 0
        hwnd = window
        screenshots = []
        for idx in range(max_scrolls + 1):
            full_screenshot = capture_window(hwnd)
            if full_screenshot:
                sidebar_width = int(full_screenshot.width * 0.3)
                screenshots.append(
                    full_screenshot.crop((0, 0, sidebar_width, full_screenshot.height))
                )
            if idx >= max_scrolls:
                break
            self.scroll_sidebar(window, "down")
            time.sleep(0.4)

        if not screenshots:
            print("[WARN] No sidebar screenshots were captured for chat-name whitelist.")
            return []

        first_width, first_height = screenshots[0].size
        stitch_started = time.perf_counter()
        stitched_image = stitch_screenshots(
            images=screenshots,
            scroll_region=CropRegion(0, 0, first_width, first_height),
            match_top_trim=0,
            match_bottom_trim=0,
        )
        if stitched_image is None:
            print("[WARN] Failed to stitch sidebar screenshots for chat-name whitelist.")
            return []

        log_vision_timing(
            "win_sidebar_names",
            "stitched",
            input_frames=len(screenshots),
            width=stitched_image.width,
            height=stitched_image.height,
            stitch_ms=round((time.perf_counter() - stitch_started) * 1000, 1),
        )

        debug_prefix = new_sidebar_debug_prefix()
        save_sidebar_crop(debug_prefix, stitched_image)
        response_str = self.vision_ai.query(
            SIDEBAR_CHAT_NAMES_PROMPT,
            stitched_image,
            max_tokens=4096,
        )
        if not response_str:
            print("[WARN] No VLM response for stitched sidebar chat-name whitelist.")
            return []

        data = parse_json_object_from_model_text(response_str)
        raw_names = data.get("names", [])
        if not isinstance(raw_names, list):
            raise TypeError("sidebar chat-name response must contain a names list")

        names: list[str] = []
        seen: set[str] = set()
        for raw_name in raw_names:
            name = str(raw_name or "").strip()
            if not name or is_sidebar_ui_chrome_label(name) or name in seen:
                continue
            seen.add(name)
            names.append(name)
        print(f"[+] Stitched sidebar whitelist identified {len(names)} chat name(s).")
        return names

    def get_sidebar_rows(self, window: Any) -> list[SidebarRow]:
        """Gets all visible rows in the sidebar using RapidOCR (names) + VLM (semantics)."""
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

        debug_prefix = new_sidebar_debug_prefix()
        rows, raw_lines, row_debug_entries = self._ocr_sidebar_rows_from_image(
            sidebar_image,
            window_left,
            window_top,
            sidebar_width,
        )
        save_sidebar_crop(debug_prefix, sidebar_image)
        print_ocr_lines("OCR raw lines", raw_lines)
        print_ocr_lines("OCR rows (no merge)", raw_lines)

        if not raw_lines:
            print("[WARN] RapidOCR returned no text; falling back to VLM-only mode.")

        # Build OCR hint list for VLM to reduce hallucination
        ocr_name_hints = [ln.text for ln in raw_lines]

        # --- Step 2: VLM — is_group / unread / y_norm per row ---
        hint_clause = ""
        if ocr_name_hints:
            names_csv = ", ".join(f'"{n}"' for n in ocr_name_hints)
            hint_clause = (
                f"\nThe OCR engine has confirmed these chat names visible top-to-bottom: [{names_csv}]. "
                "Use EXACTLY these names in your JSON; only determine is_group and unread for each."
            )

        augmented_prompt = SIDEBAR_PROMPT + hint_clause

        print(f"[DEBUG] OCR lines: {len(raw_lines)} rows, sending as hints to VLM.")

        print("[*] Querying Vision AI to analyze sidebar...")
        response_str = self.vision_ai.query(augmented_prompt, sidebar_image, max_tokens=1024)

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
        if raw_lines:
            rows, _, row_debug_entries = self._ocr_sidebar_rows_from_image(
                sidebar_image,
                window_left,
                window_top,
                sidebar_width,
                vlm_threads,
            )
        else:
            rows = threads_to_sidebar_rows(
                vlm_threads, img_width, img_height, window_left, window_top
            )
            for row in rows:
                row_debug_entries.append(make_row_debug_entry(None, row, None))

        write_sidebar_debug(debug_prefix, raw_lines, vlm_threads, row_debug_entries)
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
        raw_clicks = os.environ.get("WECLAW_WIN_CHAT_SCROLL_CLICKS", "").strip()
        scroll_amount = int(raw_clicks) if raw_clicks else 500
        if scroll_amount <= 0:
            scroll_amount = 500
        raw_bursts = os.environ.get("WECLAW_WIN_CHAT_SCROLL_BURSTS", "").strip()
        bursts = int(raw_bursts) if raw_bursts else 4
        if bursts <= 0:
            bursts = 4
        raw_settle = os.environ.get("WECLAW_WIN_CHAT_SCROLL_SETTLE_SEC", "").strip()
        settle_sec = float(raw_settle) if raw_settle else 0.04
        if settle_sec < 0:
            settle_sec = 0.04
        if direction == "up":
            clicks = scroll_amount
        elif direction == "down":
            clicks = -scroll_amount
        else:
            raise ValueError(f"Invalid scroll direction: '{direction}'. Must be 'up' or 'down'.")
        _force_foreground_window(self.hwnd)
        left, top, right, bottom = win32gui.GetWindowRect(self.hwnd)
        message_panel_x = left + int((right - left) * 0.65)
        message_panel_y = top + int((bottom - top) * 0.5)
        print(
            f"[*] Scrolling chat panel {direction} with mouse wheel "
            f"(clicks={abs(clicks)}, bursts={bursts})."
        )
        pyautogui.moveTo(message_panel_x, message_panel_y, duration=0.1)
        for _ in range(bursts):
            pyautogui.scroll(clicks)
            if settle_sec > 0:
                time.sleep(settle_sec)
        time.sleep(1.0)

    def get_chat_messages(
        self,
        chat_name: str,
        max_scrolls: int | None = None,
        skip_navigation_vlm: bool = False,
    ) -> list[ChatMessage]:
        """
        Orchestrates the process of scrolling, capturing, stitching, and extracting
        chat messages from the current chat.
        This version scrolls UP, captures, and then reverses the sequence for stitching.
        """
        print(f"[*] Starting message extraction for '{chat_name}'...")

        if skip_navigation_vlm:
            self._activate_chat_panel_by_center()
        else:
            self._activate_chat_panel_safely()
            self.click_new_messages_button()

        scroll_count = 10 if max_scrolls is None else max_scrolls
        assert scroll_count >= 0
        screenshots = []
        for i in range(scroll_count):
            self.scroll_chat_panel(direction="up")
            screenshot = capture_window(self.hwnd)
            if screenshot:
                screenshots.append(screenshot)

        if not screenshots:
            print("[WARN] No screenshots were captured.")
            return []

        stitch_session = new_chat_stitch_session_basename()
        for i, frame in enumerate(screenshots):
            save_chat_frame_before_stitch(stitch_session, chat_name, i, frame)

        print("[*] Reversing screenshot order for processing...")
        screenshots.reverse()

        all_messages = []
        chunk_size = 25
        screenshot_chunks = [screenshots[i:i + chunk_size] for i in range(0, len(screenshots), chunk_size)]
        chunk_results = []

        print(f"[*] Processing {len(screenshots)} screenshots in {len(screenshot_chunks)} chunks of size {chunk_size}.")

        for idx in range(len(screenshot_chunks) - 1, -1, -1):
            chunk = screenshot_chunks[idx]
            print(f"--- Processing chunk {idx+1}/{len(screenshot_chunks)} ---")
            if not chunk:
                continue

            stitch_started = time.perf_counter()
            stitched_image = stitch_screenshots(images=chunk, scroll_region=None)

            if not stitched_image:
                print(f"[ERROR] Failed to stitch chunk {idx+1}.")
                continue
            log_vision_timing(
                "win_chat_chunk",
                "stitched",
                chat=chat_name,
                chunk_index=idx + 1,
                chunk_total=len(screenshot_chunks),
                input_frames=len(chunk),
                width=stitched_image.width,
                height=stitched_image.height,
                stitch_ms=round((time.perf_counter() - stitch_started) * 1000, 1),
            )

            save_chat_stitch_for_vlm(stitch_session, chat_name, idx, stitched_image)

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

    def _activate_chat_panel_by_center(self) -> None:
        print("[*] Activating chat panel at deterministic center.")
        _force_foreground_window(self.hwnd)
        time.sleep(0.2)
        full_screenshot = capture_window(self.hwnd)
        if not full_screenshot:
            print("[WARN] Failed to capture window for deterministic click.")
            return
        window_left, window_top, _, _ = win32gui.GetWindowRect(self.hwnd)
        chat_panel_x1 = int(full_screenshot.width * 0.31)
        chat_panel_y1 = 50
        chat_panel_x2 = int(full_screenshot.width * 0.95)
        chat_panel_y2 = full_screenshot.height - 50
        click_x = window_left + (chat_panel_x1 + chat_panel_x2) // 2
        click_y = window_top + (chat_panel_y1 + chat_panel_y2) // 2
        pyautogui.moveTo(click_x, click_y, duration=0.1)
        pyautogui.click()
        time.sleep(0.3)

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
        response_str = self.vision_ai.query(CHAT_PANEL_SAFE_CLICK_PROMPT, chat_panel_image, max_tokens=512)

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
        1. RapidOCR returns precise text and pixel bboxes for all visible rows.
        2. VLM returns the normalized y of the highlighted row.
        3. Map VLM y back to the nearest OCR row to get the accurate name.
        """
        print("[*] Identifying current chat name from sidebar highlight...")
        full_screenshot = capture_window(self.hwnd)
        if not full_screenshot:
            print("[WARN] Failed to capture window for chat name verification.")
            return None

        sidebar_width = int(full_screenshot.width * 0.3)
        sidebar_image = full_screenshot.crop((0, 0, sidebar_width, full_screenshot.height))
        img_height = sidebar_image.height

        ocr_engine = get_ocr_engine()
        raw_lines = ocr_engine.recognize(sidebar_image)

        response_str = self.vision_ai.query(CURRENT_CHAT_Y_PROMPT, sidebar_image, max_tokens=512)

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

        response_str = self.vision_ai.query(NEW_MESSAGES_BUTTON_PROMPT, chat_panel_screenshot, max_tokens=512)

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

    def resolve_current_chat_title(self, fallback: str = "") -> str:
        full_screenshot = capture_window(self.hwnd)
        if not full_screenshot:
            return fallback
        width, height = full_screenshot.size
        x1 = int(width * 0.31)
        x2 = int(width * 0.95)
        bands = (
            (x1, int(height * 0.045), x2, int(height * 0.105)),
            (x1, int(height * 0.060), x2, int(height * 0.130)),
            (x1, 36, x2, 96),
        )
        ocr_engine = get_ocr_engine()
        for box in bands:
            crop = full_screenshot.crop(box)
            lines = ocr_engine.recognize(crop)
            candidates = [
                _clean_header_title(line.text)
                for line in sorted(lines, key=lambda ln: (ln.center_y, ln.center_x))
            ]
            for candidate in candidates:
                if _is_plausible_header_title(candidate):
                    print(f"[+] Header OCR resolved chat title: {candidate!r}")
                    return candidate
        return fallback

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


