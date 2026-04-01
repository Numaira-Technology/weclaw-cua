"""macOS platform package. Submodules load PyObjC (AppKit, Quartz) on first use."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from platform_mac.find_wechat_window import WechatWindow
    from platform_mac.mac_ai_driver import MacDriver

__all__ = [
    "MacDriver",
    "WechatWindow",
    "find_wechat_window",
    "create_driver",
    "ensure_permissions",
]


def __getattr__(name: str):
    if name == "ensure_permissions":
        from platform_mac.grant_permissions import ensure_permissions

        return ensure_permissions
    if name == "WechatWindow":
        from platform_mac.find_wechat_window import WechatWindow

        return WechatWindow
    if name == "find_wechat_window":
        from platform_mac.find_wechat_window import find_wechat_window

        return find_wechat_window
    if name == "MacDriver":
        from platform_mac.mac_ai_driver import MacDriver

        return MacDriver
    if name == "create_driver":
        from platform_mac.mac_ai_driver import MacDriver

        def create_driver():
            return MacDriver()

        return create_driver
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
