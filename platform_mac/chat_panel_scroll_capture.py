"""聊天区截图：未读条数 < 5 时不向上滚动，只截一帧；否则多次上滚并截图。"""

from __future__ import annotations

from typing import Any, List

from PIL import Image

from platform_mac import macos_window as _macos_w

SCROLL_UP_WHEN_UNREAD_AT_LEAST = 5


def scroll_capture_frames_for_extraction(driver: Any, max_messages: int | None) -> List[Image.Image]:
    skip_scroll_up = (
        max_messages is not None
        and max_messages > 0
        and max_messages < SCROLL_UP_WHEN_UNREAD_AT_LEAST
    )
    out: List[Image.Image] = []
    if skip_scroll_up:
        print(
            f"[*] 未读数 {max_messages} < {SCROLL_UP_WHEN_UNREAD_AT_LEAST}，不向上滚动，"
            "只截当前视窗。"
        )
        shot = _macos_w.capture_window_pid(driver.pid)
        if shot:
            out.append(shot)
        return out
    for _ in range(10):
        driver.scroll_chat_panel(direction="up")
        screenshot = _macos_w.capture_window_pid(driver.pid)
        if screenshot:
            out.append(screenshot)
    return out
