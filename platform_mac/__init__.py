from platform_mac.grant_permissions import ensure_permissions
from platform_mac.find_wechat_window import WechatWindow, find_wechat_window
from platform_mac.driver import MacDriver


def create_driver() -> MacDriver:
    return MacDriver()
