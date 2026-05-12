"""扫描微信 sidebar 未读会话（Mac 视觉方案）。

流程：
  1. activate_wechat
  2. capture_wechat_window_with_bounds（整窗截图，路径在 platform_mac/screenshot）
  3. detect_sidebar_region → scan_sidebar_once（require_name=False，与 rescan_unread 一致）
  4. scroll_sidebar → capture → scan → 去重
  5. 停止条件满足后返回 ChatInfo[]

去重规则：
  - 有名称按名称去重
  - 无名称按 row_rect 坐标 + badge，避免同屏多条未读被合并成一条
"""

from __future__ import annotations

import time
from typing import List, Optional

from platform_mac.chat_panel_detector import sidebar_name_matches_config_group
from platform_mac.sidebar_detector import (
    ChatInfo,
    Rect,
    detect_sidebar_region,
    scan_sidebar_once,
    sidebar_images_similar,
)

__all__ = [
    "ChatInfo",
    "list_unread_chats",
    "filter_chats_by_groups_to_monitor",
    "ocr_chat_allowed_by_groups_to_monitor",
]

MAX_SCROLL_ITERATIONS = 15
SCROLL_DELTA = -5
SETTLE_DELAY = 0.3


def _dedup_key(c: ChatInfo) -> str:
    """有名称按名称去重；无名称时用行位置 + badge，减少同屏多条未读被合并成一条。"""
    if c.name and c.name.strip():
        return c.name.strip()
    pr = c.row_rect
    if pr is not None:
        return f"__anon_{c.badge_type}_{c.unread_count}_{pr.x}_{pr.y}"
    return f"__anon_{c.badge_type}_{c.unread_count}"


def ocr_chat_allowed_by_groups_to_monitor(
    ocr_name: str,
    groups_to_monitor: Optional[List[str]],
) -> bool:
    """侧栏解析名是否被 groups_to_monitor 中任一项接受（含 config 含 emoji、OCR 无 emoji）。"""
    if not groups_to_monitor or not ocr_name or not str(ocr_name).strip():
        return False
    allowed = [g.strip() for g in groups_to_monitor if g and str(g).strip()]
    if not allowed:
        return False
    n = ocr_name.strip()
    return any(sidebar_name_matches_config_group(n, g) for g in allowed)


def filter_chats_by_groups_to_monitor(
    chats: List[ChatInfo],
    groups_to_monitor: Optional[List[str]],
) -> List[ChatInfo]:
    """只保留会话名在 groups_to_monitor 中的条目（与 config.json 的 groups_to_monitor 一致）。

    config 可含 emoji；侧栏 OCR 通常无 emoji，故按「去掉 config 中 emoji 后与 OCR 严格一致」判定。

    groups_to_monitor 为 None 或空列表时，不保留任何会话（与 run_pipeline_a 的过滤语义一致）。
    """
    if not groups_to_monitor:
        return []
    allowed = [g.strip() for g in groups_to_monitor if g and str(g).strip()]
    if not allowed:
        return []
    return [
        c
        for c in chats
        if c.name
        and c.name.strip()
        and any(sidebar_name_matches_config_group(c.name.strip(), g) for g in allowed)
    ]


def list_unread_chats(driver, max_scrolls: int = MAX_SCROLL_ITERATIONS) -> List[ChatInfo]:
    """返回 sidebar 中所有带未读标记的会话（自动滚动 + 去重）。

    driver: MacDriver 实例。
    """
    assert max_scrolls >= 0
    driver.activate_wechat()
    time.sleep(0.3)

    seen_keys: set[str] = set()
    all_chats: List[ChatInfo] = []
    prev_sidebar_img = None

    for iteration in range(max_scrolls + 1):
        img, wb = driver.capture_wechat_window_with_bounds()
        win_rect = Rect(wb.x, wb.y, wb.width, wb.height)

        sidebar_rect = detect_sidebar_region(img)
        sidebar_img = sidebar_rect.crop_from(img)

        if prev_sidebar_img is not None and sidebar_images_similar(prev_sidebar_img, sidebar_img):
            break

        visible = scan_sidebar_once(
            img,
            only_unread=True,
            require_name=False,
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

        if iteration >= max_scrolls:
            break
        driver.scroll_sidebar(SCROLL_DELTA)
        time.sleep(SETTLE_DELAY)

    driver.scroll_sidebar_to_top(max_scrolls + 2)
    time.sleep(SETTLE_DELAY)
    return all_chats
