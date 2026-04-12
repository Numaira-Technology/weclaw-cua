"""在 sidebar 未读列表中按会话名定位 ChatInfo（先滚到顶再向下翻）。

与 list_unread_chats 相同：list_unread_chats 结束时侧边栏往往在底部，
仅 rescan 当前视窗会漏掉顶部的会话；本模块通过 scroll_sidebar_to_top +
多次 scroll 与 scan 对齐可见区域。
"""

from __future__ import annotations

import time
from typing import Optional

from platform_mac.chat_panel_detector import sidebar_name_matches_config_group, titles_match
from platform_mac.sidebar_detector import ChatInfo

from algo_a.click_into_chat import rescan_unread

_MAX_SCROLL_STEPS = 18
_SCROLL_DELTA = -5
_SETTLE_SEC = 0.3


def find_unread_chat_by_name(driver, target_name: str) -> Optional[ChatInfo]:
    """在未读会话中按名称查找；找不到则向下滚动 sidebar 继续找。

    先按 sidebar_name_matches_config_group（含 config emoji 与 OCR 文本核一致），再 titles_match 兜底 OCR 轻微偏差。
    """
    assert target_name
    driver.activate_wechat()
    time.sleep(0.2)
    driver.scroll_sidebar_to_top()
    time.sleep(0.35)

    for _ in range(_MAX_SCROLL_STEPS):
        fresh = rescan_unread(driver)
        for c in fresh:
            if c.name and sidebar_name_matches_config_group(c.name, target_name):
                return c
        for c in fresh:
            if c.name and titles_match(c.name, target_name):
                return c
        driver.scroll_sidebar(_SCROLL_DELTA)
        time.sleep(_SETTLE_SEC)
    return None
