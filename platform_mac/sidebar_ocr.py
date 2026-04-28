"""HunyuanOCR sidebar crop, debug capture, and quality filtering.

Usage:
    rows = sidebar_rows_from_hunyuan(
        full_screenshot,
        window_bounds,
        ocr_engine,
    )

Input spec:
    - `full_screenshot` is a PIL image of the full WeChat window.
    - `window_bounds` is the logical macOS window bounds returned by screenshot capture.
    - `ocr_engine` exposes `decode(image)` compatible with `HunyuanOcrEngine`.

Output spec:
    - Returns sidebar rows mapped to screen coordinates.
    - Writes debug artifacts to `debug_outputs/sidebar_ocr`.
"""

from __future__ import annotations

from pathlib import Path
from time import time
from typing import Any

from PIL import Image

from platform_mac.macos_window import window_image_px_to_screen_pt
from shared.datatypes import SidebarRow
from shared.ocr_hunyuan_parser import OcrLine, normalize_text, parse_hunyuan_lines

_SIDEBAR_WIDTH_RATIO = 0.3
_TEXT_LEFT_RATIO = 0.34
_TEXT_RIGHT_RATIO = 0.98
_TEXT_TOP_RATIO = 0.06
_TEXT_BOTTOM_RATIO = 0.98
_UPSCALE = 1
_DEBUG_DIR = Path("debug_outputs/sidebar_ocr")


def _resample_filter() -> Image.Resampling:
    return Image.Resampling.LANCZOS


def _debug_prefix() -> Path:
    _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    return _DEBUG_DIR / f"sidebar_ocr_{int(time() * 1000)}"


def _is_plausible_sidebar_text(text: str) -> bool:
    normalized = normalize_text(text)
    if len(normalized) < 2:
        return False
    if len(normalized) == 2 and normalized.isascii() and normalized.isalpha():
        return False
    return True


def _sidebar_text_crop(full_screenshot: Image.Image) -> tuple[Image.Image, tuple[int, int, int, int]]:
    width, height = full_screenshot.size
    sidebar_width = int(width * _SIDEBAR_WIDTH_RATIO)
    x1 = int(sidebar_width * _TEXT_LEFT_RATIO)
    x2 = int(sidebar_width * _TEXT_RIGHT_RATIO)
    y1 = int(height * _TEXT_TOP_RATIO)
    y2 = int(height * _TEXT_BOTTOM_RATIO)
    assert x2 > x1 and y2 > y1
    crop = full_screenshot.crop((x1, y1, x2, y2))
    return crop, (x1, y1, x2, y2)


def _upscale(image: Image.Image) -> Image.Image:
    width, height = image.size
    return image.resize((width * _UPSCALE, height * _UPSCALE), _resample_filter())


def _scale_line_to_full_sidebar(line: OcrLine, crop_box: tuple[int, int, int, int]) -> OcrLine:
    x1, y1, x2, y2 = line.bbox
    crop_x, crop_y, _, _ = crop_box
    return OcrLine(
        text=line.text,
        bbox=(
            crop_x + int(x1 / _UPSCALE),
            crop_y + int(y1 / _UPSCALE),
            crop_x + int(x2 / _UPSCALE),
            crop_y + int(y2 / _UPSCALE),
        ),
        conf=line.conf,
    )


def _rows_from_lines(
    lines: list[OcrLine],
    full_screenshot: Image.Image,
    window_bounds: Any,
) -> list[SidebarRow]:
    rows: list[SidebarRow] = []
    full_width, full_height = full_screenshot.size
    sidebar_width = int(full_width * _SIDEBAR_WIDTH_RATIO)
    for ocr_line in lines:
        _, oy1, _, oy2 = ocr_line.bbox
        row_half = max((oy2 - oy1) // 2, 16)
        cy = (oy1 + oy2) // 2
        y1 = max(0, cy - row_half)
        y2 = min(full_height, cy + row_half)
        sx1, sy1 = window_image_px_to_screen_pt(0, y1, full_width, full_height, window_bounds)
        sx2, sy2 = window_image_px_to_screen_pt(
            sidebar_width,
            y2,
            full_width,
            full_height,
            window_bounds,
        )
        rows.append(
            SidebarRow(
                name=ocr_line.text,
                last_message=None,
                badge_text=None,
                bbox=(sx1, sy1, sx2, sy2),
                is_group=True,
            )
        )
    return rows


def sidebar_rows_from_hunyuan(
    full_screenshot: Image.Image,
    window_bounds: Any,
    ocr_engine: Any,
) -> list[SidebarRow]:
    crop, crop_box = _sidebar_text_crop(full_screenshot)
    upscaled = _upscale(crop)
    prefix = _debug_prefix()
    crop.save(prefix.with_suffix(".crop.png"))
    upscaled.save(prefix.with_suffix(".upscaled.png"))
    output_text = ocr_engine.decode(upscaled)
    prefix.with_suffix(".txt").write_text(output_text, encoding="utf-8")
    parsed_lines = parse_hunyuan_lines(output_text, upscaled.width, upscaled.height)
    plausible_lines = [
        _scale_line_to_full_sidebar(line, crop_box)
        for line in parsed_lines
        if _is_plausible_sidebar_text(line.text)
    ]
    if len(plausible_lines) != len(parsed_lines):
        print(
            f"[*] OCR sidebar quality filter kept "
            f"{len(plausible_lines)}/{len(parsed_lines)} line(s)."
        )
    if not plausible_lines:
        print(f"[WARN] OCR sidebar output was not plausible; debug saved to {prefix}.*")
        return []
    print(f"[*] OCR sidebar debug saved to {prefix}.*")
    return _rows_from_lines(plausible_lines, full_screenshot, window_bounds)
