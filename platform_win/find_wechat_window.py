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

from dataclasses import dataclass
from typing import Any


@dataclass
class WechatWindow:
    window_handle: int
    automation_element: Any
    pid: int


def find_wechat_window(app_name: str = "WeChat") -> WechatWindow:
    """Find the running WeChat window and return a reference to its automation element."""
    assert app_name
    raise NotImplementedError(
        "use comtypes UIAutomation.GetRootElement() to walk top-level windows, "
        "match by Name property containing app_name, "
        "extract HWND via CurrentNativeWindowHandle and pid via CurrentProcessId"
    )
