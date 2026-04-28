"""OCR wrapper for precise Chinese text recognition in WeChat sidebar.

Uses rapidocr-onnxruntime as the backend — same PaddleOCR-trained models but
running on ONNX Runtime, which avoids the oneDNN/PaddlePaddle 3.x Windows bug.

Public API is identical to the previous paddleocr-backed version.

Usage:
    from shared.ocr_paddle import get_ocr_engine, OcrLine

    engine = get_ocr_engine()
    lines = engine.recognize(pil_image)
    hit = engine.match_target(lines, "周一例会")
    if hit:
        cx = (hit.bbox[0] + hit.bbox[2]) // 2
        cy = (hit.bbox[1] + hit.bbox[3]) // 2
"""

from __future__ import annotations

import difflib
import unicodedata
from dataclasses import dataclass

import numpy as np
from PIL import Image

MIN_TRUNCATED_PREFIX_LEN = 4


@dataclass
class OcrLine:
    """A single detected text segment.

    bbox: (x1, y1, x2, y2) in *pixel* coordinates relative to the image
          that was passed to recognize().
    """

    text: str
    bbox: tuple[int, int, int, int]
    conf: float

    @property
    def center_y(self) -> int:
        return (self.bbox[1] + self.bbox[3]) // 2

    @property
    def center_x(self) -> int:
        return (self.bbox[0] + self.bbox[2]) // 2


def _poly_to_rect(box_poly: list[list[float]]) -> tuple[int, int, int, int]:
    """Convert a 4-point polygon to axis-aligned (x1,y1,x2,y2)."""
    xs = [p[0] for p in box_poly]
    ys = [p[1] for p in box_poly]
    return (int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys)))


def _normalize(text: str) -> str:
    """NFKC + strip whitespace for fuzzy comparison."""
    t = unicodedata.normalize("NFKC", text)
    t = t.replace("\u2026", "...").replace("\u22ef", "...")
    return " ".join(t.split()).strip()


def _strip_trailing_ellipsis(text: str) -> str:
    t = text.rstrip()
    while t.endswith("..."):
        t = t[:-3].rstrip()
    return t


def _safe_truncated_prefix_match(text: str, target: str) -> bool:
    prefix = _strip_trailing_ellipsis(text)
    if not prefix or len(prefix) < MIN_TRUNCATED_PREFIX_LEN:
        return False
    if len(prefix) >= len(target):
        return False
    return target.startswith(prefix) or target.casefold().startswith(prefix.casefold())


class PaddleOcrEngine:
    """Lazily-initialized singleton OCR engine (rapidocr-onnxruntime backend)."""

    _instance: "PaddleOcrEngine | None" = None

    def __new__(cls) -> "PaddleOcrEngine":
        if cls._instance is None:
            obj = object.__new__(cls)
            obj._reader = None  # type: ignore[attr-defined]
            cls._instance = obj
        return cls._instance

    def _get_reader(self):
        if self._reader is None:
            print("[*] Initializing OCR engine (rapidocr-onnxruntime, first use)...")
            try:
                from rapidocr_onnxruntime import RapidOCR  # type: ignore[import]

                self._reader = RapidOCR()
                print("[+] OCR engine initialized.")
            except ImportError as e:
                raise ImportError(
                    "rapidocr-onnxruntime is not installed. "
                    "Run: pip install rapidocr-onnxruntime"
                ) from e
        return self._reader

    def recognize(self, image: Image.Image) -> list[OcrLine]:
        """Run OCR on a PIL image and return a list of OcrLine sorted by y."""
        reader = self._get_reader()
        img_np = np.array(image.convert("RGB"))

        result, _ = reader(img_np)
        return self._parse_result(result)

    def _parse_result(self, result) -> list[OcrLine]:
        """Parse rapidocr-onnxruntime output into OcrLine list.

        Each item in result is:
            [box_points, text, confidence]
        where box_points is [[x1,y1],[x2,y2],[x3,y3],[x4,y4]] (float).
        result may be None when nothing is detected.
        """
        lines: list[OcrLine] = []
        if not result:
            return lines
        for item in result:
            if item is None or len(item) < 3:
                continue
            box_poly, text, conf = item[0], item[1], item[2]
            if not text:
                continue
            try:
                pts = [[float(p[0]), float(p[1])] for p in box_poly]
                bbox = _poly_to_rect(pts)
            except Exception:
                continue
            lines.append(OcrLine(text=str(text), bbox=bbox, conf=float(conf)))
        lines.sort(key=lambda ln: ln.center_y)
        return lines

    def merge_rows(self, lines: list[OcrLine], gap_px: int = 8) -> list[OcrLine]:
        """Merge OcrLines that are on the same visual row (within gap_px of each other).

        WeChat sidebar: each chat row has the chat name as the **top** text segment
        and a message preview snippet as the **bottom** segment.  After merging,
        each merged OcrLine's text = the topmost (chat-name) segment of the group,
        with bbox spanning the full group height.
        """
        if not lines:
            return []
        groups: list[list[OcrLine]] = []
        current_group = [lines[0]]
        for line in lines[1:]:
            prev = current_group[-1]
            prev_bottom = prev.bbox[3]
            line_top = line.bbox[1]
            if line_top <= prev_bottom + gap_px:
                current_group.append(line)
            else:
                groups.append(current_group)
                current_group = [line]
        groups.append(current_group)

        merged: list[OcrLine] = []
        for group in groups:
            group.sort(key=lambda ln: ln.center_y)
            top_line = group[0]
            all_x1 = min(ln.bbox[0] for ln in group)
            all_y1 = min(ln.bbox[1] for ln in group)
            all_x2 = max(ln.bbox[2] for ln in group)
            all_y2 = max(ln.bbox[3] for ln in group)
            merged.append(
                OcrLine(
                    text=top_line.text,
                    bbox=(all_x1, all_y1, all_x2, all_y2),
                    conf=top_line.conf,
                )
            )
        return merged

    def match_target(
        self,
        lines: list[OcrLine],
        target: str,
        min_sim: float = 0.55,
    ) -> OcrLine | None:
        """Find the OcrLine whose text best matches *target*.

        Handles:
        - Exact match (after normalisation)
        - Prefix match when UI truncates with '...'
        - Fuzzy similarity >= min_sim (SequenceMatcher ratio)
        """
        norm_target = _normalize(target)
        best: OcrLine | None = None
        best_score = -1.0

        for line in lines:
            norm_text = _normalize(line.text)

            if norm_text == norm_target:
                return line

            if _safe_truncated_prefix_match(
                norm_text, norm_target,
            ) or _safe_truncated_prefix_match(norm_target, norm_text):
                return line

            score = difflib.SequenceMatcher(None, norm_text, norm_target).ratio()
            if score > best_score:
                best_score = score
                best = line

        if best_score >= min_sim:
            return best
        return None


def get_ocr_engine() -> PaddleOcrEngine:
    """Return the singleton OCR engine, initializing it on first call."""
    return PaddleOcrEngine()
