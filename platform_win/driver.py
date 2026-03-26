"""
Windows-specific implementation of the PlatformDriver protocol using AI Vision.
"""
import json
from typing import Any

import pyautogui
import win32gui

from shared.platform_api import PlatformDriver
from shared.datatypes import SidebarRow
from platform_win.find_wechat_window import find_wechat_window as find_window
from platform_win.vision import capture_window, VisionAI, _force_foreground_window


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
Your task is to find the exact bounding box (`bbox`) for the chat item with the name "{chat_name}".
The chat sidebar is on the left side of the window.

You MUST return your response as a single, valid JSON object containing only the `bbox`.
If the specified chat item cannot be found in the image, you MUST return a JSON object with a null `bbox`, like this: `{"bbox": null}`.
The coordinates must be relative to the top-left corner of the provided image.
The `bbox` should be a list of four integers: [x_min, y_min, x_max, y_max].

Example for a chat named "Family Group":
{
  "bbox": [5, 50, 250, 100]
}
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

    def _get_precise_row_coords(self, chat_name: str) -> tuple[int, int] | None:
        """
        Captures the full window and uses the AI to find the precise coordinates
        for a specific chat name. This is used for accurate clicking.
        """
        print(f"[*] Getting precise coordinates for '{chat_name}'...")
        full_screenshot = capture_window(self.hwnd)
        if not full_screenshot:
            print(f"[WARN] Failed to capture window for precise coordinate detection.")
            return None

        prompt = COORDS_PROMPT_TEMPLATE.format(chat_name=chat_name)
        response_str = self.vision_ai.query(prompt, full_screenshot)

        if not response_str:
            print(f"[ERROR] Received no response from Vision AI for precise coordinates.")
            return None

        try:
            if "```json" in response_str:
                json_str = response_str.split("```json\n")[1].split("\n```")[0]
            else:
                json_str = response_str
            
            data = json.loads(json_str)
            relative_bbox = data.get("bbox")

            if not relative_bbox or len(relative_bbox) != 4:
                print(f"[WARN] AI returned invalid bbox for '{chat_name}': {relative_bbox}")
                return None

            # Bbox from AI is relative to the full screenshot.
            # Convert it to absolute screen coordinates.
            window_left, window_top, _, _ = win32gui.GetWindowRect(self.hwnd)
            abs_x1 = window_left + relative_bbox[0]
            abs_y1 = window_top + relative_bbox[1]
            abs_x2 = window_left + relative_bbox[2]
            abs_y2 = window_top + relative_bbox[3]

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

        # Get window position to calculate crop and absolute coordinates
        window_left, window_top, _, _ = win32gui.GetWindowRect(hwnd)

        # Crop to the sidebar (e.g., the left 30% of the window)
        sidebar_width = int(full_screenshot.width * 0.3)
        sidebar_crop_box = (0, 0, sidebar_width, full_screenshot.height)
        sidebar_image = full_screenshot.crop(sidebar_crop_box)

        print("[*] Querying Vision AI to analyze sidebar...")
        response_str = self.vision_ai.query(SIDEBAR_PROMPT, sidebar_image)

        if not response_str:
            print("[ERROR] Received no response from Vision AI for sidebar analysis.")
            return []

        try:
            # The AI might return a string containing a JSON code block.
            # We need to extract the raw JSON.
            if "```json" in response_str:
                json_str = response_str.split("```json\n")[1].split("\n```")[0]
            else:
                json_str = response_str
            
            sidebar_data = json.loads(json_str)
        except (json.JSONDecodeError, IndexError) as e:
            print(f"[ERROR] Failed to parse JSON response from Vision AI: {e}")
            print(f"Raw response was: {response_str}")
            return []

        # Convert the parsed data into SidebarRow objects with absolute screen coordinates
        sidebar_rows = []
        for item in sidebar_data:
            # Bbox from AI is relative to the cropped sidebar image.
            # Convert it to absolute screen coordinates.
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

    def click_row(self, row: Any) -> None:
        """Clicks on the center of a given SidebarRow."""
        if not isinstance(row, SidebarRow):
            print(f"[ERROR] Cannot click on type {type(row)}, expected SidebarRow.")
            return

        _force_foreground_window(self.hwnd)

        # Get precise coordinates just before clicking to ensure accuracy.
        coords = self._get_precise_row_coords(row.name)
        if not coords:
            print(f"[ERROR] Could not get precise coordinates for '{row.name}'. Aborting click.")
            return

        center_x, center_y = coords

        print(f"[*] Preparing to click on row '{row.name}' at screen coordinates: ({center_x}, {center_y})")
        
        # Move the mouse to the target over a short duration to make it visible
        pyautogui.moveTo(center_x, center_y, duration=0.5)
        
        # Perform the click at the current mouse location
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


