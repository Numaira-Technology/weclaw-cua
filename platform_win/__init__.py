from platform_win.grant_permissions import ensure_permissions
from platform_win.find_wechat_window import WechatWindow, find_wechat_window
from platform_win.driver import WinDriver


def create_driver() -> WinDriver:
    return WinDriver()
