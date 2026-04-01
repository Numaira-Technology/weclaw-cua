"""左侧窄栏「消息」图标：基于红色角标与固定槽位的点击点估计（窗口截图像素坐标系）。

用于 macOS 微信 / 飞书类布局：最左图标列宽度固定，第二枚常为会话列表入口；
未读角标为红色团块。返回值为整窗截图中的 (ix, iy)，供 window_image_px_to_screen_pt 映射。
"""

from __future__ import annotations

from typing import Tuple

import numpy as np
from PIL import Image

from platform_mac.sidebar_detector import BADGE_PIXEL_MIN, TITLEBAR_HEIGHT_RATIO, _red_mask

ICON_RAIL_WIDTH_FRAC = 0.068
ICON_BAND_MAX_FRAC = 0.38

SECOND_ICON_CENTER_Y_FRAC = 0.115
SECOND_ICON_CENTER_X_FRAC = 0.48


def nav_messages_unread_badge_present(img: Image.Image) -> bool:
    """左栏上部是否存在与未读角标尺度相近的红色聚类。"""
    w, h = img.size
    tb = int(h * TITLEBAR_HEIGHT_RATIO)
    rw = max(56, int(w * ICON_RAIL_WIDTH_FRAC))
    y1 = min(h, tb + int((h - tb) * ICON_BAND_MAX_FRAC))
    rail = img.crop((0, tb, rw, y1))
    arr = np.asarray(rail)[:, :, :3]
    mask = _red_mask(arr)
    if int(mask.sum()) < BADGE_PIXEL_MIN:
        return False
    ys, xs = np.where(mask)
    return len(xs) >= BADGE_PIXEL_MIN


def compute_messages_nav_click_window_xy(img: Image.Image) -> Tuple[float, float]:
    """估计消息图标中心在整窗截图中的像素坐标（有角标时偏置，否则用第二图标几何槽位）。"""
    w, h = img.size
    tb = int(h * TITLEBAR_HEIGHT_RATIO)
    rw = max(56, int(w * ICON_RAIL_WIDTH_FRAC))
    rail = img.crop((0, tb, rw, h))
    arr = np.asarray(rail)[:, :, :3]
    mask = _red_mask(arr)
    ys, xs = np.where(mask)
    usable = len(xs) >= BADGE_PIXEL_MIN
    if usable:
        band_rows = int(rail.height * 0.52)
        sub = mask[:band_rows, :]
        ys2, xs2 = np.where(sub)
        if len(xs2) >= BADGE_PIXEL_MIN // 2:
            bcx = float(xs2.mean())
            bcy = float(ys2.mean())
            ix = bcx - rw * 0.22
            iy = tb + bcy + rail.height * 0.06
            ix = max(rw * 0.28, min(ix, rw * 0.72))
            iy = max(tb + rail.height * 0.05, min(iy, tb + rail.height * 0.45))
            return (ix, iy)

    slot_top = tb + int((h - tb) * SECOND_ICON_CENTER_Y_FRAC)
    ix = rw * SECOND_ICON_CENTER_X_FRAC
    iy = float(min(max(slot_top, tb + 30), tb + int((h - tb) * 0.32)))
    return (ix, iy)
