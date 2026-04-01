"""Locate the WeChat application window via Windows UI Automation.

Usage:
    from platform_win.find_wechat_window import find_wechat_window
    window = find_wechat_window("WeChat")

Input spec:
    - app_name: the window title prefix, e.g. "WeChat" or "微信".

Output spec:
    - Returns a WechatWindow dataclass with window_handle (HWND),
      automation_element (IUIAutomationElement), and pid.
    - Crashes if WeChat is not running or no window is found.

Notes:
    Uses the comtypes/UIAutomationCore COM interface to walk the
    desktop's top-level windows and match by window title.
"""

import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32


def find_wechat_window(
    class_name: str = "Qt51514QWindowIcon", app_name: str = "微信"
) -> int:
    """Finds the main WeChat window and returns its handle (HWND).

    This function is more specific than searching by title alone, as it also
    specifies the window class name, which is less likely to have duplicates.

    Args:
        class_name: The class name of the WeChat window.
        app_name: The window name (title) of the WeChat application.

    Returns:
        The window handle (HWND) as an integer, or 0 if not found.
    """
    hwnd = user32.FindWindowW(class_name, app_name)
    if not hwnd:
        print(
            f"[ERROR] Window with class '{class_name}' and title '{app_name}' not found. "
            f"Please ensure WeChat is running."
        )
        return 0
    return hwnd

