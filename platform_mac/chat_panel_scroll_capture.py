"""聊天区截图：未读 ≤5 时少量上滚（2 次），超过 5 则完整滚动（10 次）。"""

from __future__ import annotations

from typing import Any, List

from PIL import Image

SCROLL_UP_WHEN_UNREAD_AT_LEAST = 5
LIGHT_SCROLL_COUNT = 2
FULL_SCROLL_COUNT = 10


def scroll_capture_frames_for_extraction(
    driver: Any,
    max_messages: int | None,
    max_scrolls: int | None = None,
) -> List[Image.Image]:
    light_scroll = (
        max_messages is not None
        and max_messages > 0
        and max_messages <= SCROLL_UP_WHEN_UNREAD_AT_LEAST
    )
    if light_scroll:
        scroll_count = LIGHT_SCROLL_COUNT
        print(f"[*] 未读数 {max_messages} <= {SCROLL_UP_WHEN_UNREAD_AT_LEAST}，轻量上滚 {scroll_count} 次。")
    else:
        scroll_count = FULL_SCROLL_COUNT
        print(f"[*] 未读数较多，完整上滚 {scroll_count} 次。")
    if max_scrolls is not None:
        assert max_scrolls >= 0
        scroll_count = min(scroll_count, max_scrolls)
        print(f"[*] 聊天框上滑次数上限: {max_scrolls}；本次执行 {scroll_count} 次。")

    from platform_mac import macos_window as _macos_w

    out: List[Image.Image] = []
    current = _macos_w.capture_window_pid(driver.pid)
    if current:
        out.append(current)

    for _ in range(scroll_count):
        driver.scroll_chat_panel(direction="up")
        screenshot = _macos_w.capture_window_pid(driver.pid)
        if screenshot:
            out.append(screenshot)
    return out
