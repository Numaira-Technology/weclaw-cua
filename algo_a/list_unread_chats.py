"""扫描微信 sidebar 未读会话（Mac 视觉方案）。

流程：
  1. activate_wechat
  2. capture_wechat_window
  3. scan_sidebar_once
  4. scroll_sidebar → capture → scan → 去重
  5. 停止条件满足后返回 ChatInfo[]

去重规则：
  - 优先按 name 去重（name 非空时）
  - name 为空时按 badge 特征做弱去重
"""

from __future__ import annotations

import time
from typing import List

from platform_mac.sidebar_detector import (
    ChatInfo,
    Rect,
    detect_sidebar_region,
    scan_sidebar_once,
    sidebar_images_similar,
)

__all__ = ["ChatInfo", "list_unread_chats"]

MAX_SCROLL_ITERATIONS = 15
SCROLL_DELTA = -5
SETTLE_DELAY = 0.3


def _dedup_key(c: ChatInfo) -> str:
    if c.name:
        return c.name
    return f"__anon_{c.badge_type}_{c.unread_count}"


def list_unread_chats(driver) -> List[ChatInfo]:
    """返回 sidebar 中所有带未读标记的会话（自动滚动 + 去重）。

    driver: MacDriver 实例。
    """
    driver.activate_wechat()
    time.sleep(0.3)

    seen_keys: set[str] = set()
    all_chats: List[ChatInfo] = []
    prev_sidebar_img = None

    for iteration in range(MAX_SCROLL_ITERATIONS):
        img, wb = driver.capture_wechat_window_with_bounds()
        win_rect = Rect(wb.x, wb.y, wb.width, wb.height)

        sidebar_rect = detect_sidebar_region(img)
        sidebar_img = sidebar_rect.crop_from(img)

        if prev_sidebar_img is not None and sidebar_images_similar(prev_sidebar_img, sidebar_img):
            break

        visible = scan_sidebar_once(
            img,
            only_unread=True,
            require_name=True,
            window_bounds=win_rect,
        )

        new_found = 0
        for chat in visible:
            key = _dedup_key(chat)
            if key not in seen_keys:
                seen_keys.add(key)
                all_chats.append(chat)
                new_found += 1

        prev_sidebar_img = sidebar_img

        if iteration > 0 and new_found == 0:
            break

        driver.scroll_sidebar(SCROLL_DELTA)
        time.sleep(SETTLE_DELAY)

    driver.scroll_sidebar_to_top()
    time.sleep(SETTLE_DELAY)
    return all_chats
