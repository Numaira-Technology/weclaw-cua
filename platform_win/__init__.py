from .driver import WinDriver
from .find_wechat_window import find_wechat_window
from .vision import capture_window

__all__ = ["WinDriver", "create_driver", "find_wechat_window", "capture_window"]


def create_driver():
    return WinDriver()
