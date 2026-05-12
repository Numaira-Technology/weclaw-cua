"""Sidebar list JSON from vision: branch Ashley-scroll-function `modules/group_classifier.py`.

`parse_classification` logic for threads + y (0–1000) → `SidebarRow` with synthetic row bbox.
"""

import json
from typing import Any

from shared.datatypes import SidebarRow
from shared.sidebar_ui_chrome import is_sidebar_ui_chrome_label


def strip_markdown_code_fence(text: str) -> str:
    text = text.strip()
    if not text.startswith("```"):
        return text
    lines = text.split("\n")
    lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def parse_threads_json(text_output: str) -> list[dict[str, Any]]:
    text = strip_markdown_code_fence(text_output)
    payload = json.loads(text)
    if isinstance(payload, list):
        return payload
    return list(payload.get("threads", []))


def threads_to_sidebar_rows(
    threads: list[dict[str, Any]],
    sidebar_image_width: int,
    sidebar_image_height: int,
    window_left: int,
    window_top: int,
    *,
    full_window_width_px: int | None = None,
    full_window_height_px: int | None = None,
    window_width_pt: int | None = None,
    window_height_pt: int | None = None,
) -> list[SidebarRow]:
    rows: list[SidebarRow] = []
    mac_pts = (
        full_window_width_px is not None
        and full_window_height_px is not None
        and window_width_pt is not None
        and window_height_pt is not None
    )
    for item in threads:
        name = str(item.get("name", ""))
        if is_sidebar_ui_chrome_label(name):
            continue
        y_norm = float(item.get("y", 0))
        unread = bool(item.get("unread", False))
        is_group = bool(item.get("is_group", False))
        selected = bool(item.get("selected", item.get("is_selected", False)))
        y_center = int(y_norm / 1000.0 * sidebar_image_height)
        row_half = max(int(24 / 1000.0 * sidebar_image_height), 12)
        y1 = max(0, y_center - row_half)
        y2 = min(sidebar_image_height, y_center + row_half)
        ub = item.get("unread_badge")
        if unread:
            if ub is not None and str(ub).strip():
                badge = str(ub).strip()
            else:
                badge = "1"
        else:
            badge = None
        if mac_pts:
            assert full_window_height_px and full_window_width_px
            sy = window_height_pt / full_window_height_px
            sx = window_width_pt / full_window_width_px
            left_pt = window_left + int(0 * sx)
            right_pt = window_left + int(sidebar_image_width * sx)
            top_pt = window_top + int(y1 * sy)
            bottom_pt = window_top + int(y2 * sy)
            box = (left_pt, top_pt, right_pt, bottom_pt)
        else:
            box = (
                window_left,
                window_top + y1,
                window_left + sidebar_image_width,
                window_top + y2,
            )
        rows.append(
            SidebarRow(
                name=name,
                last_message=None,
                badge_text=badge,
                bbox=box,
                is_group=is_group,
                selected=selected,
            )
        )
    return rows


def unread_cap_from_badge_text(badge_text: str | None, *, max_cap: int = 200) -> int:
    """从侧栏角标字符串解析要读取的最新消息条数上限（纯红点按 1）。"""
    if not badge_text or not str(badge_text).strip():
        return 1
    s = str(badge_text).strip().replace("⋯", "").replace("…", "")
    if s.endswith("+"):
        s = s[:-1].strip()
    digits = "".join(ch for ch in s if ch.isdigit())
    if not digits:
        return 1
    v = int(digits)
    return min(max(1, v), max_cap)
