"""Scroll the WeChat sidebar to the top before a full sidebar scan."""

import time
from typing import Any

from shared.platform_api import PlatformDriver


def scroll_sidebar_to_top(driver: PlatformDriver, window: Any) -> None:
    print("[*] Scrolling sidebar to the top...")
    for _ in range(10):
        driver.scroll_sidebar(window, "up")
        time.sleep(0.1)
