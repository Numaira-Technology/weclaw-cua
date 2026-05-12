"""Scroll the WeChat sidebar to the top before a full sidebar scan."""

import time
from typing import Any

from shared.platform_api import PlatformDriver


def scroll_sidebar_to_top(
    driver: PlatformDriver,
    window: Any,
    max_down_scrolls: int = 16,
) -> None:
    print("[*] Scrolling sidebar to the top...")
    assert max_down_scrolls >= 0
    scroll_up = getattr(driver, "scroll_sidebar", None)
    if scroll_up is None:
        return
    for _ in range(max_down_scrolls + 2):
        scroll_up(window, "up")
        time.sleep(0.1)
