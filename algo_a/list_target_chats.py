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

import time
from dataclasses import dataclass
from typing import Any

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
        # The row object from the AI driver is the source of truth.
        # The `is_unread` logic depends on the badge_text detected by the AI.
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
    # To detect when we're stuck, we track all unique chat names seen across scrolls.
    all_seen_chat_names = set()
    # To stop when all targets are seen, regardless of read status.
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
                # Check if this chat is unread
                if chat.is_unread:
                    # Add it to our list if we haven't already found it
                    if chat.name not in found_chats:
                        print(f"    [+] Found unread target chat to process: {chat.name}")
                        found_chats[chat.name] = chat

            if chat.name not in all_seen_chat_names:
                new_chats_found_this_scroll = True
                all_seen_chat_names.add(chat.name)

        # Early exit condition: if we have found all target chats we are looking for.
        if target_set.issubset(seen_target_names):
            print("[*] All target chats have been found. Stopping scan.")
            break

        # If this scroll didn't reveal any new chats we haven't seen before, we're at the end.
        if i > 0 and not new_chats_found_this_scroll:
            print("[*] Reached the end of the sidebar. Stopping scan.")
            break

        print(f"[*] Scrolling sidebar down... (iteration {i+1}/{MAX_SCROLL_ITERATIONS})")
        driver.scroll_sidebar(window, "down")
        time.sleep(1)  # Add a delay for stability to prevent crashes


    if not found_chats:
        print("[*] No unread target chats were found.")
    
    return list(found_chats.values())
