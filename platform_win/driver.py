"""
Windows-specific implementation of the PlatformDriver protocol using AI Vision.
"""
import json
import shutil
import time
from pathlib import Path
from typing import Any

import pyautogui
import win32gui

from shared.platform_api import PlatformDriver
from shared.datatypes import SidebarRow, ChatMessage
from platform_win.find_wechat_window import find_wechat_window as find_window
from platform_win.vision import capture_window, VisionAI, _force_foreground_window
from utils.image_stitcher import stitch_screenshots, CropRegion
from PIL import Image


SIDEBAR_PROMPT = '''
You are an expert UI automation assistant. Analyze the provided screenshot of a chat application's sidebar.
Your task is to identify every individual chat item visible.

For each chat item, you must extract the following information:
1.  `name`: The name of the person or group chat.
2.  `last_message`: The preview of the last message. If there is no message preview, this should be null.
3.  `badge_text`: The text content of any unread notification badge. This could be a number (e.g., "1", "99+"), a red dot (return "red_dot"), or a specific phrase (e.g., "[x条未读]"). If there is no badge, this should be null.
4.  `bbox`: The precise bounding box for the entire chat item row, as a list of four integers: [x_min, y_min, x_max, y_max]. The coordinates must be relative to the provided image.

You MUST return your response as a single, valid JSON object, which is a list of the chat items you found. Do not include any other text or explanations in your response.

Example response format:
[
  {
    "name": "Family Group",
    "last_message": "Mom: See you tonight!",
    "badge_text": "3",
    "bbox": [5, 50, 250, 100]
  },
  {
    "name": "John Doe",
    "last_message": "Sounds good, thanks!",
    "badge_text": null,
    "bbox": [5, 101, 250, 151]
  }
]
'''


COORDS_PROMPT_TEMPLATE = '''
You are a precision UI automation assistant. You will be given a screenshot of an entire chat application window.
Your task is to find the exact bounding box (`bbox`) for the chat item with the name "{chat_name}", which is located in the sidebar on the left.
Pay close attention to the exact name provided. You must find the item that precisely matches this name, not one with a similar name.

You MUST return your response as a single, valid JSON object containing only the `bbox`.
If the specified chat item cannot be found in the image, you MUST return a JSON object with a null `bbox`, like this: `{{ "bbox": null }}`.
The coordinates must be relative to the top-left corner of the provided image.
The `bbox` should be a list of four integers: [x_min, y_min, x_max, y_max].

Example for a chat named "Family Group":
{{
  "bbox": [5, 50, 250, 100]
}}
'''

NEW_MESSAGES_BUTTON_PROMPT = '''
Analyze the screenshot of the chat panel. If you see a button indicating "xx new messages" or similar, return its bounding box.
Respond in JSON format with a single key "bbox" which is a list of four numbers [x1, y1, x2, y2] representing the bounding box of the button.
If no such button is visible, return {"bbox": null}.
'''

CHAT_HEADER_PROMPT = '''
You are a UI analysis assistant. Analyze the provided screenshot of a chat application's header.
Your task is to identify the name of the currently open chat or group.
Return a single JSON object with one key, "chat_name".

Example:
{
  "chat_name": "Family Group"
}
'''

CHAT_PANEL_PROMPT = '''
You are an expert UI automation assistant. Analyze the provided screenshot of a chat application's main chat panel.
Your task is to identify every individual message visible and extract its details.

For each message, you must extract the following information:
1.  `sender`: The name of the person who sent the message. If it's a system message (like a timestamp or notification), the sender should be `null`.
2.  `content`: The text content of the message. For non-text messages like images or files, provide a placeholder like `[Image]` or `[File]`.
3.  `time`: The timestamp associated with the message. This is often displayed near the message bubble or as a separate centered item (e.g., "Yesterday 10:45 PM"). If a message doesn't have an explicit timestamp right next to it, you can associate it with the nearest preceding timestamp in the chat. If no timestamp is visible for a message, set this to `null`.
4.  `type`: The type of message. This can be 'text', 'image', 'file', 'system' (for timestamps or notifications like "You recalled a message"), 'recalled', etc.

- Messages from others are on the left, with the sender's name above the message bubble.
- Messages from "You" (the user) are on the right, and do not have a visible sender name. You should explicitly set the sender to "You".
- System messages (like timestamps, "You recalled a message", etc.) are centered and have no sender. The sender should be `null` and the type should be 'system'.

Respond with a JSON object containing a single key "messages", which is a list of message objects.
Each message object must have the keys "sender", "content", "time", and "type".

Example:
```json
{
  "messages": [
    {
      "sender": "龚格非",
      "content": "天呐",
      "time": "2026年2月5日 0:53",
      "type": "text"
    },
    {
      "sender": "You",
      "content": "好的",
      "time": "2026年2月5日 0:54",
      "type": "text"
    },
    {
      "sender": null,
      "content": "You recalled a message",
      "time": "2026年2月5日 0:55",
      "type": "recalled"
    }
  ]
}
```
'''


class WinDriver(PlatformDriver):
    def __init__(self):
        self.hwnd: int = 0
        self.vision_ai = VisionAI()

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
        Captures the full window and uses the AI to find the precise coordinates
        for a specific chat name. This is used for accurate clicking.
        """
        chat_name = row.name
        print(f"[*] Getting precise coordinates for '{chat_name}' using full screenshot...")
        full_screenshot = capture_window(self.hwnd)
        if not full_screenshot:
            print(f"[WARN] Failed to capture window for precise coordinate detection.")
            return None

        window_rect = win32gui.GetWindowRect(self.hwnd)
        window_left, window_top, _, _ = window_rect

        print(f"[DEBUG] Precise coord prompt chat_name: '{chat_name}'")
        prompt = COORDS_PROMPT_TEMPLATE.format(chat_name=chat_name)
        response_str = self.vision_ai.query(prompt, full_screenshot)

        if not response_str:
            print(f"[ERROR] Received no response from Vision AI for precise coordinates.")
            return None

        print(f"[DEBUG] Raw AI response for precise coords:\n{response_str}")

        try:
            if "```json" in response_str:
                json_str = response_str.split("```json\n")[1].split("\n```")[0]
            else:
                json_str = response_str

            data = json.loads(json_str)
            win_rel_bbox = data.get("bbox")

            if not win_rel_bbox or len(win_rel_bbox) != 4:
                print(f"[WARN] AI returned invalid bbox for '{chat_name}': {win_rel_bbox}")
                print(f"[DEBUG] Raw AI response for invalid bbox: {response_str}")
                return None

            abs_x1 = window_left + win_rel_bbox[0]
            abs_y1 = window_top + win_rel_bbox[1]
            abs_x2 = window_left + win_rel_bbox[2]
            abs_y2 = window_top + win_rel_bbox[3]

            center_x = (abs_x1 + abs_x2) // 2
            center_y = (abs_y1 + abs_y2) // 2

            print(f"[+] Precise coordinates for '{chat_name}' found: ({center_x}, {center_y})")
            return (center_x, center_y)

        except Exception as e:
            print(f"[ERROR] Failed to parse precise coordinate response for '{chat_name}'. Exception type: {type(e)}, message: {e}")
            print(f"Raw response was: {response_str}")
            return None

    def get_sidebar_rows(self, window: Any) -> list[SidebarRow]:
        """Gets all visible rows in the sidebar using the Vision AI."""
        hwnd = window
        if not self.vision_ai.client:
            print("[ERROR] Vision AI client not initialized. Cannot get sidebar rows.")
            return []

        full_screenshot = capture_window(hwnd)
        if not full_screenshot:
            print("[WARN] Failed to capture window for sidebar row detection.")
            return []

        window_left, window_top, _, _ = win32gui.GetWindowRect(hwnd)

        sidebar_width = int(full_screenshot.width * 0.3)
        sidebar_crop_box = (0, 0, sidebar_width, full_screenshot.height)
        sidebar_image = full_screenshot.crop(sidebar_crop_box)

        print("[*] Querying Vision AI to analyze sidebar...")
        response_str = self.vision_ai.query(SIDEBAR_PROMPT, sidebar_image)

        if not response_str:
            print("[ERROR] Received no response from Vision AI for sidebar analysis.")
            return []

        try:
            if "```json" in response_str:
                json_str = response_str.split("```json\n")[1].split("\n```")[0]
            else:
                json_str = response_str
            
            sidebar_data = json.loads(json_str)
        except (json.JSONDecodeError, IndexError) as e:
            print(f"[ERROR] Failed to parse JSON response from Vision AI: {e}")
            print(f"Raw response was: {response_str}")
            return []

        sidebar_rows = []
        for item in sidebar_data:
            relative_bbox = item.get("bbox")
            if not relative_bbox or len(relative_bbox) != 4:
                print(f"[WARN] Skipping item with invalid bbox: {item}")
                continue

            abs_x1 = window_left + relative_bbox[0]
            abs_y1 = window_top + relative_bbox[1]
            abs_x2 = window_left + relative_bbox[2]
            abs_y2 = window_top + relative_bbox[3]

            sidebar_rows.append(
                SidebarRow(
                    name=item.get("name", ""),
                    last_message=item.get("last_message"),
                    badge_text=item.get("badge_text"),
                    bbox=(abs_x1, abs_y1, abs_x2, abs_y2),
                )
            )
        
        print(f"[+] AI identified {len(sidebar_rows)} sidebar rows.")
        return sidebar_rows

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
        """Scrolls the chat panel area up or down."""
        print(f"[*] Scrolling chat panel {direction}...")
        window_rect = win32gui.GetWindowRect(self.hwnd)
        window_left, window_top, _, _ = window_rect

        chat_panel_region = self._get_chat_panel_region()
        
        scroll_x = window_left + (chat_panel_region[0] + chat_panel_region[2]) // 2
        scroll_y = window_top + (chat_panel_region[1] + chat_panel_region[3]) // 2

        pyautogui.moveTo(scroll_x, scroll_y, duration=0.2)

        pyautogui.click()

        key_to_press = 'pagedown' if direction == "down" else 'pageup'
        print(f"[*] Scrolling {direction} using '{key_to_press}' key.")
        pyautogui.press(key_to_press)
        time.sleep(1.0)

    def get_chat_messages(self, chat_name: str) -> list[ChatMessage]:
        """
        Orchestrates the process of scrolling, capturing, stitching, and extracting
        chat messages from the current chat.
        This version scrolls UP, captures, and then reverses the sequence for stitching.
        """
        print(f"[*] Starting message extraction for '{chat_name}'...")

        self.click_new_messages_button()

        screenshots = []
        for i in range(10):
            self.scroll_chat_panel(direction="up")
            time.sleep(0.5)
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

        print(f"[*] Processing {len(screenshots)} screenshots in {len(screenshot_chunks)} chunks of size {chunk_size}.")

        window_rect = win32gui.GetWindowRect(self.hwnd)
        window_width = window_rect[2] - window_rect[0]
        window_height = window_rect[3] - window_rect[1]
        scroll_region = CropRegion(
            x=int(window_width * 0.31),
            y=50,
            w=int(window_width * 0.64),
            h=window_height - 100
        )

        for i, chunk in enumerate(screenshot_chunks):
            print(f"--- Processing chunk {i+1}/{len(screenshot_chunks)} ---")
            if not chunk:
                continue

            stitched_image = stitch_screenshots(
                images=chunk,
                scroll_region=scroll_region
            )

            if not stitched_image:
                print(f"[ERROR] Failed to stitch chunk {i+1}.")
                continue

            try:
                response_str = self.vision_ai.query(CHAT_PANEL_PROMPT, stitched_image)
            except Exception as e:
                print(f"[ERROR] Vision AI query for chunk {i+1} failed: {e}")
                continue

            if not response_str:
                print(f"[ERROR] No response from AI for message extraction on chunk {i+1}.")
                continue

            try:
                if "```json" in response_str:
                    json_str = response_str.split("```json\n")[1].split("\n```")[0]
                else:
                    json_str = response_str

                data = json.loads(json_str)
                messages_data = data.get("messages", [])
                chunk_messages = []

                for j, msg_data in enumerate(messages_data):
                    if "content" not in msg_data:
                        print(f"[WARN] Chunk {i+1}, Msg {j+1}: Skipping message due to missing 'content': {msg_data}")
                        continue

                    try:
                        chunk_messages.append(ChatMessage(**msg_data))
                    except TypeError as e:
                        print(f"[WARN] Chunk {i+1}, Msg {j+1}: Skipping message during creation: {msg_data}. Error: {e}")

                if chunk_messages:
                    print(f"[+] Extracted {len(chunk_messages)} messages from chunk {i+1}.")
                    all_messages.extend(chunk_messages)
                else:
                    print(f"[WARN] No valid messages extracted from chunk {i+1}.")

            except Exception as e:
                print(f"[ERROR] Failed to parse messages from AI response for chunk {i+1}: {e}")
                print(f"Raw response was: {response_str}")
                continue

        print(f"[*] Finished processing all chunks. Total messages extracted: {len(all_messages)}")
        return all_messages

    def get_current_chat_name(self) -> str | None:
        """Captures the header of the chat panel and uses AI to get the current chat name."""
        print("[*] Identifying current chat name...")
        full_screenshot = capture_window(self.hwnd)
        if not full_screenshot:
            print("[WARN] Failed to capture window for chat name verification.")
            return None

        header_crop_box = (
            int(full_screenshot.width * 0.31),
            0,
            int(full_screenshot.width * 0.9),
            int(full_screenshot.height * 0.1)
        )
        header_image = full_screenshot.crop(header_crop_box)

        response_str = self.vision_ai.query(CHAT_HEADER_PROMPT, header_image)

        if not response_str:
            print(f"[ERROR] Received no response from Vision AI for chat name.")
            return None

        try:
            if "```json" in response_str:
                json_str = response_str.split("```json\n")[1].split("\n```")[0]
            else:
                json_str = response_str
            
            data = json.loads(json_str)
            chat_name = data.get("chat_name")

            if chat_name:
                print(f"[+] Current chat identified as: '{chat_name}'")
                return chat_name
            else:
                print(f"[WARN] AI did not return a chat_name.")
                return None

        except (json.JSONDecodeError, KeyError) as e:
            print(f"[ERROR] Failed to parse chat name response. Exception: {e}")
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
            if "```json" in response_str:
                json_str = response_str.split("```json\n")[1].split("\n```")[0]
            else:
                json_str = response_str

            data = json.loads(json_str)
            bbox = data.get("bbox")

            if not bbox:
                print("[DEBUG] No 'new messages' button found by AI.")
                return False

            abs_x1 = window_left + chat_panel_region[0] + bbox[0]
            abs_y1 = window_top + chat_panel_region[1] + bbox[1]
            abs_x2 = window_left + chat_panel_region[0] + bbox[2]
            abs_y2 = window_top + chat_panel_region[1] + bbox[3]

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

        coords = self._get_precise_row_coords(row)
        if not coords:
            print(f"[ERROR] Could not get precise coordinates for '{row.name}'. Aborting click.")
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


