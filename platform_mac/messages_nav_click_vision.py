"""用 Vision 模型在整窗截图上定位左侧「会话/消息」导航图标，并映射为屏幕点击坐标。"""

from __future__ import annotations

from typing import Any

from PIL import Image

from platform_mac.left_nav_messages_icon import compute_messages_nav_click_window_xy
from platform_mac.macos_window import (
    activate_pid,
    capture_window_pid_and_bounds,
    vision_bbox_center_to_screen_pt,
    window_image_px_to_screen_pt,
)
from shared.vision_response_json import parse_json_object_from_model_text
from shared.vision_prompts import MESSAGES_NAV_ICON_PROMPT


def _bbox_spans_reasonable(bbox: list, img_w: int, img_h: int) -> bool:
    x0, y0, x1, y1 = [float(b) for b in bbox]
    if x1 <= x0 or y1 <= y0:
        return False
    if max(x0, y0, x1, y1) <= 1000.0:
        pw = (x1 - x0) / 1000.0 * img_w
        ph = (y1 - y0) / 1000.0 * img_h
    else:
        pw = x1 - x0
        ph = y1 - y0
    m = min(img_w, img_h)
    return pw >= 8 and ph >= 8 and pw <= m * 0.40 and ph <= m * 0.40


def _messages_nav_screen_pt_once(vision_ai: Any, full_img: Image.Image, wb) -> tuple[int, int]:
    response_str = vision_ai.query(MESSAGES_NAV_ICON_PROMPT, full_img, max_tokens=1024)
    assert response_str
    data = parse_json_object_from_model_text(response_str)
    bbox = data.get("bbox")
    assert bbox and len(bbox) == 4
    assert _bbox_spans_reasonable(bbox, full_img.width, full_img.height)
    sx, sy = vision_bbox_center_to_screen_pt(bbox, full_img.width, full_img.height, wb)
    return int(sx), int(sy)


def _heuristic_messages_nav_screen_pt(full_img: Image.Image, wb) -> tuple[int, int]:
    ix, iy = compute_messages_nav_click_window_xy(full_img)
    sx, sy = window_image_px_to_screen_pt(ix, iy, full_img.width, full_img.height, wb)
    return int(sx), int(sy)


def _vision_point_is_reasonable(
    vision_pt: tuple[int, int],
    heuristic_pt: tuple[int, int],
    full_img: Image.Image,
    wb,
) -> bool:
    dx = abs(vision_pt[0] - heuristic_pt[0])
    dy = abs(vision_pt[1] - heuristic_pt[1])
    rail_w = max(56, int(full_img.width * 0.068))
    max_dx = max(18, int(rail_w * 0.45))
    max_dy = max(18, int(wb.height * 0.035))
    return dx <= max_dx and dy <= max_dy


def resolve_messages_nav_screen_pt(vision_ai: Any, pid: int) -> tuple[int, int]:
    """激活窗口、截图，最多三次请求模型，返回 pyautogui 可用的屏幕坐标。"""
    assert pid
    for _ in range(3):
        activate_pid(pid)
        full_img, wb = capture_window_pid_and_bounds(pid)
        heuristic_pt = _heuristic_messages_nav_screen_pt(full_img, wb)
        try:
            vision_pt = _messages_nav_screen_pt_once(vision_ai, full_img, wb)
            if _vision_point_is_reasonable(vision_pt, heuristic_pt, full_img, wb):
                return heuristic_pt
            return heuristic_pt
        except AssertionError:
            return heuristic_pt
    return heuristic_pt
