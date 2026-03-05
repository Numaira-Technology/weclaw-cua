"""
Reusable utilities for cropping screenshots and translating coordinates.

Usage:
    from modules.crop_utils import CropRegion, get_regions

    regions = get_regions(os_type)   # "windows" or "macos"

    # Crop a screenshot
    cropped_bytes = regions.chat_list.crop_image(screenshot_bytes)

    # Convert cropped pixel coords back to screen coords
    screen_x, screen_y = regions.chat_list.to_screen_coords(crop_x, crop_y)

    # Convert 0-1000 normalized coords to screen coords (for AI responses)
    screen_x, screen_y = regions.member_select.normalized_to_screen_coords(500, 300)

Input:
    - img_bytes: PNG screenshot as bytes
    - crop_x, crop_y: Pixel coordinates within the cropped image
    - normalized_x, normalized_y: 0-1000 normalized coordinates from AI
    - os_type: "windows" or "macos"

Output:
    - crop_image: Cropped PNG as bytes
    - to_screen_coords: (screen_x, screen_y) tuple for clicking
    - normalized_to_screen_coords: (screen_x, screen_y) from 0-1000 space
    - get_regions: ScreenRegions dataclass with platform-appropriate CropRegion instances

Region reference (all SCREEN coordinates, absolute pixels):

  Windows 2560x1440:
    chat_list:      x=(58, 276),   y=(0, 1440)   → 218x1440px sidebar
    member_panel:   x=(2300, 2560), y=(0, 1440)  → 260x1440px right panel
    member_select:  x=(925, 1630),  y=(425, 970) → 705x545px  centre dialog

  macOS 2560x1600 (WeChat Mac full-screen):
    chat_list:      x=(70, 310),   y=(0, 1600)   → 240x1600px sidebar
    member_panel:   x=(1980, 2560), y=(0, 1600)  → 580x1600px right panel
    member_select:  x=(830, 1730),  y=(430, 1050) → 900x620px centre dialog

  macOS coordinates are tuned for a 2560x1600 Retina display with WeChat Mac
  filling most of the screen.  Adjust in get_regions() if your layout differs.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Tuple

from PIL import Image


@dataclass
class CropRegion:
    """Defines a crop region with coordinate translation.

    All boundary values (x_start, x_end, y_start, y_end) are in SCREEN COORDINATES.

    Coordinate systems:
    - SCREEN: Absolute pixel position on the display (used for clicking)
    - CROP: Pixel position within the cropped image (0,0 = top-left of crop)
    - NORMALIZED: 0-1000 scale relative to crop dimensions (used by AI vision)

    Conversion methods:
    - to_screen_coords(): CROP → SCREEN
    - normalized_to_screen_coords(): NORMALIZED → SCREEN
    """

    x_start: int  # SCREEN: left edge of crop region
    x_end: int    # SCREEN: right edge of crop region
    y_start: int  # SCREEN: top edge of crop region
    y_end: int    # SCREEN: bottom edge of crop region

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
        """
        crop_x = int((normalized_x / 1000.0) * self.width)
        crop_y = int((normalized_y / 1000.0) * self.height)
        return self.to_screen_coords(crop_x, crop_y)


@dataclass
class ScreenRegions:
    """Platform-specific crop regions for the three WeChat UI areas.

    Fields:
    - chat_list:     sidebar listing all chats (used for classification + click-to-open)
    - member_panel:  group info / member panel on the right (used for minus button area)
    - member_select: centre dialog for selecting members to remove
    """

    chat_list: CropRegion
    member_panel: CropRegion
    member_select: CropRegion


# =============================================================================
# Windows 2560x1440 regions  (all coordinates in SCREEN space)
# =============================================================================
_WINDOWS_REGIONS = ScreenRegions(
    chat_list=CropRegion(x_start=58, x_end=276, y_start=0, y_end=1440),
    member_panel=CropRegion(x_start=2300, x_end=2560, y_start=0, y_end=1440),
    member_select=CropRegion(x_start=925, x_end=1630, y_start=425, y_end=970),
)

# =============================================================================
# macOS 2560x1600 regions  (WeChat Mac near-full-screen layout)
# Adjust these values if your WeChat window position or display differs.
# =============================================================================
_MACOS_REGIONS = ScreenRegions(
    chat_list=CropRegion(x_start=70, x_end=310, y_start=0, y_end=1600),
    member_panel=CropRegion(x_start=1980, x_end=2560, y_start=0, y_end=1600),
    member_select=CropRegion(x_start=830, x_end=1730, y_start=430, y_end=1050),
)


def get_regions(os_type: str) -> ScreenRegions:
    """Return the correct ScreenRegions for the given os_type.

    Args:
        os_type: "macos" or "windows" (from ComputerSettings.os_type)

    Returns:
        ScreenRegions with platform-appropriate CropRegion instances
    """
    if os_type == "macos":
        return _MACOS_REGIONS
    return _WINDOWS_REGIONS


# ---------------------------------------------------------------------------
# Legacy module-level constants — kept for backward compatibility.
# New code should use get_regions(os_type) instead.
# ---------------------------------------------------------------------------
CHAT_LIST_REGION = _WINDOWS_REGIONS.chat_list
MEMBER_PANEL_REGION = _WINDOWS_REGIONS.member_panel
MEMBER_SELECT_REGION = _WINDOWS_REGIONS.member_select
