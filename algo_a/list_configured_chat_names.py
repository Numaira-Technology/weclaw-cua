"""Resolve sidebar rows for each name in config `groups_to_monitor` (unread not required)."""

from typing import Any

from algo_a.list_target_chats_win import ChatInfo, _row_key, list_target_chats
from algo_a.sidebar_scroll_to_top import scroll_sidebar_to_top
from shared.platform_api import PlatformDriver


def list_chats_by_configured_names(
    driver: PlatformDriver,
    window: Any,
    names: list[str],
    *,
    unread_only: bool = False,
    max_scrolls: int = 10,
) -> list[ChatInfo]:
    assert window is not None
    assert isinstance(names, list)
    found: dict[str, ChatInfo] = {}
    seen_cfg: set[str] = set()
    for raw in names:
        cfg = str(raw).strip()
        if not cfg or cfg in seen_cfg:
            continue
        seen_cfg.add(cfg)
        scroll_sidebar_to_top(driver, window, sidebar_max_scrolls=max_scrolls)
        matches = list_target_chats(
            driver,
            window,
            name_filter=cfg,
            unread_only=unread_only,
            max_scrolls=max_scrolls,
        )
        for chat in matches:
            k = _row_key(chat.name)
            if k not in found:
                found[k] = chat
    return list(found.values())
