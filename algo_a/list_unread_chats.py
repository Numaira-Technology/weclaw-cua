"""Scan the WeChat sidebar UI tree for chats with unread message badges.

Usage:
    from algo_a.list_unread_chats import list_unread_chats
    chats = list_unread_chats(window)

Input spec:
    - window: WechatWindow reference from platform_mac.

Output spec:
    - Returns list[ChatInfo] for every chat row that has an unread badge.
    - Each ChatInfo contains the chat name, unread count, and the AXUIElement ref.

Notes:
    - The sidebar may require scrolling to reveal all chat rows.
    - Must scroll the sidebar incrementally to discover chats beyond the visible area.
    - Badge count is parsed from the badge AX attribute (may be a number or "...").
"""

from dataclasses import dataclass
from typing import Any

from platform_mac.find_wechat_window import WechatWindow


@dataclass
class ChatInfo:
    name: str
    unread_count: int
    ui_element: Any


def list_unread_chats(window: WechatWindow) -> list[ChatInfo]:
    """Return all sidebar chats that have unread badges, scrolling as needed."""
    assert window is not None
    raise NotImplementedError(
        "navigate to sidebar AXList, iterate AXRow children, "
        "check for unread badge, scroll sidebar if needed to reveal more rows"
    )
