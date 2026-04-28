"""Pure parser helpers for HunyuanOCR text spotting output.

Usage:
    from shared.ocr_hunyuan_parser import parse_hunyuan_lines

    lines = parse_hunyuan_lines("<ref>Inbox</ref><quad>(10,20),(100,40)</quad>", 300, 200)

Input spec:
    - Accepts raw HunyuanOCR decoded text from the line-spotting prompt.
    - Coordinates may be `<ref>text</ref><quad>...</quad>` or plain
      `text (x1,y1),(x2,y2)` records.
    - Coordinates may use two rectangle corners or a four-point quadrilateral.

Output spec:
    - Returns `OcrLine` rows sorted by vertical position.
    - `bbox` values are clipped pixel coordinates relative to the source image.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_NUM_RE = r"-?\d+(?:\.\d+)?"
_POINT_RE = re.compile(rf"\(\s*({_NUM_RE})\s*,\s*({_NUM_RE})\s*\)")
_REF_QUAD_RE = re.compile(
    r"<ref>(?P<text>.*?)</ref>\s*<quad>\s*(?P<points>.*?)\s*</quad>",
    re.DOTALL,
)
_TEXT_BOX_RE = re.compile(
    r"(?P<text>[^\n<>()]+?)\s*"
    r"(?P<points>\([^)]*\)\s*,\s*\([^)]*\)(?:\s*,\s*\([^)]*\))*)"
)


@dataclass
class OcrLine:
    """A single HunyuanOCR text line."""

    text: str
    bbox: tuple[int, int, int, int]
    conf: float = 1.0

    @property
    def center_y(self) -> int:
        return (self.bbox[1] + self.bbox[3]) // 2

    @property
    def center_x(self) -> int:
        return (self.bbox[0] + self.bbox[2]) // 2


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u2026", "...").replace("\u22ef", "...")
    text = text.strip("\\ ")
    return " ".join(text.split()).strip()


def _to_pixel_bbox(
    points: list[tuple[float, float]],
    image_width: int,
    image_height: int,
) -> tuple[int, int, int, int]:
    max_abs = max(abs(coord) for point in points for coord in point)
    if max_abs <= 1.0:
        points = [(x * image_width, y * image_height) for x, y in points]
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    left = int(round(min(xs)))
    top = int(round(min(ys)))
    right = int(round(max(xs)))
    bottom = int(round(max(ys)))
    return (
        max(0, min(left, image_width)),
        max(0, min(top, image_height)),
        max(0, min(right, image_width)),
        max(0, min(bottom, image_height)),
    )


def _parse_points(text: str) -> list[tuple[float, float]]:
    return [(float(x), float(y)) for x, y in _POINT_RE.findall(text)]


def parse_hunyuan_lines(text: str, image_width: int, image_height: int) -> list[OcrLine]:
    lines: list[OcrLine] = []
    for pattern in (_REF_QUAD_RE, _TEXT_BOX_RE):
        for match in pattern.finditer(text):
            line_text = normalize_text(match.group("text"))
            if not line_text:
                continue
            points = _parse_points(match.group("points"))
            if len(points) < 2:
                continue
            bbox = _to_pixel_bbox(points, image_width, image_height)
            if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
                continue
            lines.append(OcrLine(text=line_text, bbox=bbox))
        if lines:
            break
    lines.sort(key=lambda line: (line.center_y, line.bbox[0]))
    return lines
