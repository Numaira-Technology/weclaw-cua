"""Scan the WeChat sidebar for targets: unread groups, or configured names (config.json groups_to_monitor).

Vision supplies `unread` + `is_group`. Pass `unread_only=True` to require `is_unread` for selection.

Usage:
    list_target_chats(driver, window)
    list_target_chats(driver, window, all_groups=True)
    list_target_chats(driver, window, name_filter="706-纽约2群")
"""

import os
import re
import sys
import time
import unicodedata
from dataclasses import dataclass
from typing import Any

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from shared.platform_api import PlatformDriver

MIN_TRUNCATED_PREFIX_LEN = 4
# Truncated sidebar vs longer config name: stems shorter than this are treated as ambiguous
# (see test_configured_name_rejects_short_truncated_prefix: "运营" must not match 运营核心群…).
MIN_REVERSE_SIDEBAR_PREFIX_LEN = 3


@dataclass
class ChatInfo:
    name: str
    ui_element: Any
    is_unread: bool
    is_group: bool | None


def _normalize_chat_label(text: str) -> str:
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)
    t = t.replace("…", "...").replace("⋯", "...")
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\U0001F900-\U0001F9FF"
        "\U0001FA00-\U0001FAFF"
        "\u2600-\u26FF"
        "\u2700-\u27BF"
        "\uFE0F\u200D\u200C"
        "]+",
        flags=re.UNICODE,
    )
    t = emoji_pattern.sub("", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _badge_means_unread(badge_text: str | None) -> bool:
    if badge_text is None:
        return False
    s = str(badge_text).strip()
    if not s:
        return False
    if s.lower() in ("null", "none"):
        return False
    return True


def _sidebar_compact_compare(s: str) -> str:
    t = s.replace(" ", "").replace("\u3000", "")
    t = t.replace("·", "-").replace("・", "-")
    return t


def _chat_identity_key(text: str) -> str:
    clean = _normalize_chat_label(text)
    chars = []
    for ch in clean:
        category = unicodedata.category(ch)
        if category[0] in ("P", "S", "Z"):
            continue
        chars.append(ch.casefold())
    return "".join(chars)


def _strip_trailing_ellipsis(text: str) -> str:
    t = text.rstrip()
    while True:
        stripped = t.rstrip(".。．…⋯").rstrip()
        if stripped == t:
            return t
        t = stripped


def _safe_truncated_prefix_match(ui_name: str, filter_name: str) -> bool:
    prefix = _strip_trailing_ellipsis(ui_name)
    if not prefix or len(prefix) < MIN_TRUNCATED_PREFIX_LEN:
        return False
    if len(prefix) >= len(filter_name):
        return False
    if filter_name.startswith(prefix):
        return True

    compact_prefix = _sidebar_compact_compare(prefix)
    compact_filter = _sidebar_compact_compare(filter_name)
    if len(compact_prefix) < MIN_TRUNCATED_PREFIX_LEN:
        return False
    if len(compact_prefix) >= len(compact_filter):
        return False
    if compact_filter.startswith(compact_prefix):
        return True

    identity_prefix = _chat_identity_key(prefix)
    identity_filter = _chat_identity_key(filter_name)
    if len(identity_prefix) < MIN_TRUNCATED_PREFIX_LEN:
        return False
    if len(identity_prefix) >= len(identity_filter):
        return False
    return identity_filter.startswith(identity_prefix)


def _sidebar_names_match(ui_name: str, filter_name: str) -> bool:
    if not ui_name or not filter_name:
        return False
    clean_ui = _normalize_chat_label(ui_name)
    want = _normalize_chat_label(filter_name)
    if clean_ui == want:
        return True
    cu_c = _sidebar_compact_compare(clean_ui)
    w_c = _sidebar_compact_compare(want)
    if cu_c == w_c:
        return True
    # Config name shorter than OCR label (counts, parentheses, subtitle) — prefix still matches.
    if len(w_c) >= 2 and len(cu_c) >= len(w_c) and cu_c.startswith(w_c):
        return True
    # Sidebar shows a truncated stem of the configured label (compact OCR strictly shorter).
    if (
        len(cu_c) >= MIN_REVERSE_SIDEBAR_PREFIX_LEN
        and len(w_c) > len(cu_c)
        and w_c.startswith(cu_c)
    ):
        return True
    return _safe_truncated_prefix_match(clean_ui, want)


def _row_key(name: str) -> str:
    n = _normalize_chat_label(name)
    return n if n else name


def _collect_visible_chats(driver: PlatformDriver, window: Any) -> list[ChatInfo]:
    rows = driver.get_sidebar_rows(window)
    results = []
    for row in rows:
        raw_is_group = getattr(row, "is_group", None)
        results.append(
            ChatInfo(
                name=row.name,
                ui_element=row,
                is_unread=_badge_means_unread(row.badge_text),
                is_group=None if raw_is_group is None else bool(raw_is_group),
            )
        )
    return results


def _chat_type_allows_unknown_group(is_group: bool | None, chat_type: str) -> bool:
    assert chat_type in ("group", "private", "all")
    if is_group is None:
        return True
    return (
        chat_type == "all"
        or (chat_type == "group" and is_group)
        or (chat_type == "private" and not is_group)
    )


def list_target_chats(
    driver: PlatformDriver,
    window: Any,
    name_filter: str | None = None,
    *,
    all_groups: bool = False,
    unread_only: bool = False,
    chat_type: str = "group",
    max_scrolls: int = 10,
) -> list[ChatInfo]:
    assert window is not None
    assert not (name_filter and all_groups)
    assert chat_type in ("group", "private", "all")
    assert max_scrolls >= 0

    found_chats: dict[str, ChatInfo] = {}
    all_seen_chat_names = set()

    if name_filter:
        ur = " + unread badge" if unread_only else ""
        print(
            f"[*] Sidebar scan (match name{ur}, chat_type={chat_type!r}), "
            f"re-locating: {name_filter!r}"
        )
    elif all_groups:
        ur = " + unread badge" if unread_only else ""
        print(f"[*] Sidebar scan: configured wildcard chat_type={chat_type!r}{ur}.")
    else:
        print("[*] Sidebar scan: unread group chats only (is_group + unread).")

    for i in range(max_scrolls + 1):
        visible_chats = _collect_visible_chats(driver, window)

        if not visible_chats:
            print("[WARN] Got no visible chats from driver. Stopping scan.")
            break

        new_chats_found_this_scroll = False

        print(f"--- Iteration {i + 1}: Processing {len(visible_chats)} visible chats ---")
        for chat in visible_chats:
            clean = _normalize_chat_label(chat.name)
            if name_filter:
                want_row = _sidebar_names_match(chat.name, name_filter)
                if unread_only:
                    want_row = want_row and chat.is_unread
            elif all_groups:
                want_row = _chat_type_allows_unknown_group(chat.is_group, chat_type)
                if unread_only:
                    want_row = want_row and chat.is_unread
            else:
                want_row = chat.is_unread and _chat_type_allows_unknown_group(
                    chat.is_group,
                    "group",
                )

            print(
                f"  - Seen: {chat.name!r} (Norm: {clean!r}, Is group: {chat.is_group}, "
                f"Is Unread: {chat.is_unread}, Select: {want_row})"
            )

            if want_row:
                key = _row_key(chat.name)
                if key not in found_chats:
                    print(f"    [+] Queued: {chat.name!r}")
                    found_chats[key] = chat

            if chat.name not in all_seen_chat_names:
                new_chats_found_this_scroll = True
                all_seen_chat_names.add(chat.name)

        if i > 0 and not new_chats_found_this_scroll:
            print("[*] Reached the end of the sidebar. Stopping scan.")
            break

        if name_filter and found_chats:
            print("[*] Located filtered chat. Stopping scan.")
            break

        if i >= max_scrolls:
            print(f"[*] Reached sidebar max scrolls ({max_scrolls}). Stopping scan.")
            break

        print(f"[*] Scrolling sidebar down... (iteration {i + 1}/{max_scrolls})")
        driver.scroll_sidebar(window, "down")
        time.sleep(1)

    out = list(found_chats.values())
    print(f"[DEBUG] Returning {len(out)} sidebar match(es).")
    return out
