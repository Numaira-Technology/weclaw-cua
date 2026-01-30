"""
Reusable utilities for cropping screenshots and translating coordinates.

Usage:
    from modules.crop_utils import (
        CropRegion,
        CHAT_LIST_REGION,
        MEMBER_PANEL_REGION,
        MEMBER_SELECT_REGION,
    )

    # Crop a screenshot
    cropped_bytes = CHAT_LIST_REGION.crop_image(screenshot_bytes)

    # Convert cropped pixel coords back to screen coords
    screen_x, screen_y = CHAT_LIST_REGION.to_screen_coords(crop_x, crop_y)

    # Convert 0-1000 normalized coords to screen coords (for AI responses)
    screen_x, screen_y = MEMBER_SELECT_REGION.normalized_to_screen_coords(500, 300)

Input:
    - img_bytes: PNG screenshot as bytes
    - crop_x, crop_y: Pixel coordinates within the cropped image
    - normalized_x, normalized_y: 0-1000 normalized coordinates from AI

Output:
    - crop_image: Cropped PNG as bytes
    - to_screen_coords: (screen_x, screen_y) tuple for clicking
    - normalized_to_screen_coords: (screen_x, screen_y) from 0-1000 space
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Tuple

from PIL import Image


@dataclass
class CropRegion:
    """Defines a crop region with coordinate translation for 2560x1440 screen.

    All boundary values (x_start, x_end, y_start, y_end) are in SCREEN COORDINATES.

    Coordinate systems:
    - SCREEN: Absolute pixel position on 2560x1440 display (used for clicking)
    - CROP: Pixel position within the cropped image (0,0 = top-left of crop)
    - NORMALIZED: 0-1000 scale relative to crop dimensions (used by AI vision)

    Conversion methods:
    - to_screen_coords(): CROP → SCREEN
    - normalized_to_screen_coords(): NORMALIZED → SCREEN
    """

    x_start: int  # SCREEN: left edge of crop region
    x_end: int  # SCREEN: right edge of crop region
    y_start: int  # SCREEN: top edge of crop region
    y_end: int  # SCREEN: bottom edge of crop region

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
        """Convert CROP coordinates to SCREEN coordinates.

        Args:
            crop_x: X position in CROP space (pixels from left edge of crop)
            crop_y: Y position in CROP space (pixels from top edge of crop)

        Returns:
            (screen_x, screen_y): Position in SCREEN space (absolute pixels)
        """
        return (crop_x + self.x_start, crop_y + self.y_start)

    def normalized_to_screen_coords(
        self, normalized_x: int, normalized_y: int
    ) -> Tuple[int, int]:
        """Convert NORMALIZED coordinates to SCREEN coordinates.

        This is the primary method for converting AI vision responses to click positions.

        Args:
            normalized_x: X in NORMALIZED space (0=left, 1000=right of crop)
            normalized_y: Y in NORMALIZED space (0=top, 1000=bottom of crop)

        Returns:
            (screen_x, screen_y): Position in SCREEN space (absolute pixels)

        Example for MEMBER_SELECT_REGION (925-1630, 425-970):
            normalized (500, 500) → crop (352, 272) → screen (1277, 697)
        """
        # NORMALIZED → CROP
        crop_x = int((normalized_x / 1000.0) * self.width)
        crop_y = int((normalized_y / 1000.0) * self.height)
        # CROP → SCREEN
        return self.to_screen_coords(crop_x, crop_y)


# =============================================================================
# Predefined crop regions for 2560x1440 WeChat desktop
# All coordinates are in SCREEN space (absolute pixels)
# =============================================================================

# Chat list sidebar: left side of WeChat window
# SCREEN coords: x=(58, 276), y=(0, 1440) → 218x1440 pixels
# Used for: Thread classification, clicking on chats
CHAT_LIST_REGION = CropRegion(x_start=58, x_end=276, y_start=0, y_end=1440)

# Member panel right strip: right side info panel
# SCREEN coords: x=(2300, 2560), y=(0, 1440) → 260x1440 pixels
# Used for: Verifying panel opened, minus button, removal verification
MEMBER_PANEL_REGION = CropRegion(x_start=2300, x_end=2560, y_start=0, y_end=1440)

# Member selection dialog: center popup for selecting users to remove
# SCREEN coords: x=(925, 1630), y=(425, 970) → 705x545 pixels
# Used for: Finding and clicking user checkboxes in removal dialog
MEMBER_SELECT_REGION = CropRegion(x_start=925, x_end=1630, y_start=425, y_end=970)
