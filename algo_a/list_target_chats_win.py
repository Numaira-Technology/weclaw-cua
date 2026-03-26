"""Scan the WeChat sidebar to find all chats specified in a target list.

Usage:
    from algo_a.list_target_chats import list_target_chats
    chats = list_target_chats(driver, window, targets)

Input spec:
    - driver: PlatformDriver instance.
    - window: platform-specific window handle.
    - targets: A list of chat names (str) to find.

Output spec:
    - Returns list[ChatInfo] for every located target chat.
"""

import sys
import os
import time
from dataclasses import dataclass
from typing import Any

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from shared.platform_api import PlatformDriver

MAX_SCROLL_ITERATIONS = 50


@dataclass
class ChatInfo:
    name: str
    ui_element: Any
    is_unread: bool


def _collect_visible_chats(driver: PlatformDriver, window: Any) -> list[ChatInfo]:
    """Scan currently visible sidebar rows and return their info."""
    rows = driver.get_sidebar_rows(window)
    results = []
    for row in rows:
        is_unread = row.badge_text is not None and row.badge_text != ""
        results.append(
            ChatInfo(name=row.name, ui_element=row, is_unread=is_unread)
        )
    return results


def list_target_chats(driver: PlatformDriver, window: Any, targets: list[str]) -> list[ChatInfo]:
    """
    Scrolls through the sidebar to find all chats that are in the target list AND are unread.
    """
    assert window is not None

    target_set = set(targets)
    found_chats: dict[str, ChatInfo] = {}
    all_seen_chat_names = set()
    seen_target_names = set()

    print(f"[*] Starting sidebar scan for unread target chats. Targets: {list(target_set)}")

    for i in range(MAX_SCROLL_ITERATIONS):
        visible_chats = _collect_visible_chats(driver, window)

        if not visible_chats:
            print("[WARN] Got no visible chats from driver. Stopping scan.")
            break

        new_chats_found_this_scroll = False

        print(f"--- Iteration {i+1}: Processing {len(visible_chats)} visible chats ---")
        for chat in visible_chats:
            is_target = chat.name in target_set
            print(f"  - Seen: '{chat.name}' (Is Target: {is_target}, Is Unread: {chat.is_unread})")

            if is_target:
                seen_target_names.add(chat.name)
                if chat.is_unread:
                    if chat.name not in found_chats:
                        print(f"    [+] Found unread target chat to process: {chat.name}")
                        found_chats[chat.name] = chat

            if chat.name not in all_seen_chat_names:
                new_chats_found_this_scroll = True
                all_seen_chat_names.add(chat.name)

        if target_set.issubset(seen_target_names):
            print("[*] All target chats have been found. Stopping scan.")
            break

        if i > 0 and not new_chats_found_this_scroll:
            print("[*] Reached the end of the sidebar. Stopping scan.")
            break

        print(f"[*] Scrolling sidebar down... (iteration {i+1}/{MAX_SCROLL_ITERATIONS})")
        driver.scroll_sidebar(window, "down")
        time.sleep(1)

    print(f"[DEBUG] Returning {len(found_chats)} unread chats.")
    return list(found_chats.values())
