"""Scroll the chat message panel to the very bottom so all unread messages are loaded.

Usage:
    from algo_a.scroll_chat_to_bottom import scroll_chat_to_bottom
    scroll_chat_to_bottom(driver, window)

Input spec:
    - driver: PlatformDriver instance.
    - window: platform-specific window handle.

Output spec:
    - None. Side effect: the message scroll area is at the bottom.
"""

import time
from typing import Any

from shared.platform_api import PlatformDriver

MAX_SCROLL_ITERATIONS = 100
SCROLL_SETTLE_DELAY = 0.15


def scroll_chat_to_bottom(driver: PlatformDriver, window: Any) -> None:
    """Scroll the message area to the bottom, waiting for lazy-loaded content."""
    assert window is not None

    prev_position = -1.0

    for _ in range(MAX_SCROLL_ITERATIONS):
        current_position = driver.get_message_scroll_position(window)

        if current_position >= 1.0:
            break

        if current_position == prev_position:
            break

        prev_position = current_position
        driver.scroll_messages(window, "down")
        time.sleep(SCROLL_SETTLE_DELAY)
