"""Scan the WeChat sidebar for chats with unread message badges.

Usage:
    from algo_a.list_unread_chats import list_unread_chats
    chats = list_unread_chats(driver, window)

Input spec:
    - driver: PlatformDriver instance from platform_mac or platform_win.
    - window: platform-specific window handle from driver.find_wechat_window().

Output spec:
    - Returns list[ChatInfo] for every chat row that has an unread badge.
    - Each ChatInfo contains the chat name, unread count, and the UI element ref.
    - unread_count is -1 for muted chats with a dot badge (count unknown).
"""

from dataclasses import dataclass
from typing import Any

from shared.platform_api import PlatformDriver

MAX_SCROLL_ITERATIONS = 50


@dataclass
class ChatInfo:
    name: str
    unread_count: int
    ui_element: Any


def _parse_badge_count(badge_text: str | None) -> int | None:
    """Parse badge text into an integer count.

    Returns None if no badge, -1 if muted dot (empty string), or the numeric count.
    '99+' and similar overflow markers are returned as 99.
    """
    if badge_text is None:
        return None
    if badge_text == "":
        return -1
    cleaned = badge_text.replace("+", "").strip()
    if cleaned.isdigit():
        return int(cleaned)
    return -1


def _collect_visible_unread(driver: PlatformDriver, window: Any) -> list[ChatInfo]:
    """Scan currently visible sidebar rows and return those with unread badges."""
    rows = driver.get_sidebar_rows(window)
    results = []
    for row in rows:
        badge_text = driver.get_row_badge_text(row)
        count = _parse_badge_count(badge_text)
        if count is None:
            continue
        name = driver.get_row_name(row)
        results.append(ChatInfo(name=name, unread_count=count, ui_element=row))
    return results


def list_unread_chats(driver: PlatformDriver, window: Any) -> list[ChatInfo]:
    """Return all sidebar chats that have unread badges, scrolling as needed."""
    assert window is not None

    seen_names: set[str] = set()
    all_chats: list[ChatInfo] = []

    for _ in range(MAX_SCROLL_ITERATIONS):
        visible = _collect_visible_unread(driver, window)

        new_found = False
        for chat in visible:
            if chat.name not in seen_names:
                seen_names.add(chat.name)
                all_chats.append(chat)
                new_found = True

        if not new_found:
            break

        driver.scroll_sidebar(window, "down")

    return all_chats
