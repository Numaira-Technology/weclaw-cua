"""Detect whether a WeChat sidebar row is the currently selected green row."""

from __future__ import annotations

import numpy as np
from PIL import Image

_TEXT_AREA_X0_RATIO = 0.18
_TEXT_AREA_X1_RATIO = 0.96
_GREEN_RATIO_THRESHOLD = 0.08


def row_has_selected_green_background(row_img: Image.Image) -> bool:
    """Return True when the row's text/background area is dominated by WeChat green."""
    rgb = row_img.convert("RGB")
    arr = np.array(rgb).astype(np.int16)
    h, w, _ = arr.shape
    if h <= 0 or w <= 0:
        return False
    x0 = min(max(int(w * _TEXT_AREA_X0_RATIO), 0), w - 1)
    x1 = min(max(int(w * _TEXT_AREA_X1_RATIO), x0 + 1), w)
    region = arr[:, x0:x1, :]
    if region.size == 0:
        return False
    r = region[:, :, 0]
    g = region[:, :, 1]
    b = region[:, :, 2]
    mask = (g >= 110) & (g > r + 25) & (g > b + 20) & (r <= 150) & (b <= 180)
    return float(mask.mean()) >= _GREEN_RATIO_THRESHOLD
