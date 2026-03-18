"""Locate the WeChat application window via macOS Accessibility API.

Usage:
    from platform_mac.find_wechat_window import find_wechat_window
    window = find_wechat_window("WeChat")

Input spec:
    - app_name: the application name as shown in macOS, e.g. "WeChat" or "微信".

Output spec:
    - Returns a WechatWindow dataclass with app_ref, window_ref, and pid.
    - Crashes if WeChat is not running or no window is found.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class WechatWindow:
    app_ref: Any
    window_ref: Any
    pid: int


def find_wechat_window(app_name: str = "WeChat") -> WechatWindow:
    """Find the running WeChat app and return a reference to its main window."""
    assert app_name
    raise NotImplementedError(
        "use NSWorkspace.sharedWorkspace().runningApplications to find pid, "
        "then AXUIElementCreateApplication(pid) to get app_ref, "
        "then query AXWindows for window_ref"
    )
