"""
Reusable utilities for cropping screenshots and translating coordinates.

Usage:
    from modules.crop_utils import CropRegion, CHAT_LIST_REGION

    # Crop a screenshot
    cropped_bytes = CHAT_LIST_REGION.crop_image(screenshot_bytes)

    # Convert cropped coords back to screen coords
    screen_x, screen_y = CHAT_LIST_REGION.to_screen_coords(crop_x, crop_y)

Input:
    - img_bytes: PNG screenshot as bytes
    - crop_x, crop_y: Coordinates within the cropped image

Output:
    - crop_image: Cropped PNG as bytes
    - to_screen_coords: (screen_x, screen_y) tuple for clicking
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Tuple

from PIL import Image


@dataclass
class CropRegion:
    """Defines a crop region with coordinate translation for 2560x1440 screen."""

    x_start: int
    x_end: int
    y_start: int
    y_end: int

    @property
    def width(self) -> int:
        return self.x_end - self.x_start

    @property
    def height(self) -> int:
        return self.y_end - self.y_start

    def crop_image(self, img_bytes: bytes) -> bytes:
        """Crop image bytes to this region, return PNG bytes."""
        img = Image.open(io.BytesIO(img_bytes))
        cropped = img.crop((self.x_start, self.y_start, self.x_end, self.y_end))
        buffer = io.BytesIO()
        cropped.save(buffer, format="PNG")
        return buffer.getvalue()

    def to_screen_coords(self, crop_x: int, crop_y: int) -> Tuple[int, int]:
        """Convert cropped image coords to full screen coords."""
        return (crop_x + self.x_start, crop_y + self.y_start)


# Predefined crop regions for 2560x1440 WeChat desktop
# Chat list sidebar: x range (58, 276), full height
CHAT_LIST_REGION = CropRegion(x_start=58, x_end=276, y_start=0, y_end=1440)
