"""Stitch vertically scrolled chat screenshots into one long image.

Assumes each screenshot is a full-window capture of a chat UI. Only the
scrollable content region is stitched; a fixed header (top) and footer
(input area) are taken from the first and last screenshot respectively.
Overlap between consecutive frames is estimated via edge detection and
template matching so that duplicate content is removed when stacking.

Usage:
    from pathlib import Path
    output = stitch_screenshots(
        screenshot_paths=[Path("pass0.png"), Path("pass1.png"), ...],
        output_path=Path("stitched.png"),
        write_output=True,
    )

Input:
    screenshot_paths: List of paths to PNG/JPEG images in scroll order (top to bottom).
    output_path: Where to write the stitched image.
    write_output: If True, write the result to output_path.
    scroll_region: CropRegion (x, y, w, h) defining the scrollable area to stitch.
        Default SCROLLABLE_REGION is tuned for the target chat UI (header excluded).

Output:
    Dict with "pair_overlaps" (pixel overlap per adjacent pair), "match_scores"
    (template-match confidence 0–1), and "output_path" (str or "").
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List
import cv2
import numpy as np


@dataclass(frozen=True)
class CropRegion:
    x: int
    y: int
    w: int
    h: int


SCROLLABLE_REGION = CropRegion(x=0, y=94, w=2264, h=1390)


def _load_and_crop(path: Path, region: CropRegion) -> np.ndarray:
    """Load image from path and crop to region in one pass (no encode/decode round-trip)."""
    img_bytes = path.read_bytes()
    image = cv2.imdecode(np.frombuffer(img_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert image is not None, f"failed to decode image: {path}"
    return image[region.y : region.y + region.h, region.x : region.x + region.w]


def _estimate_overlap(prev_img: np.ndarray, curr_img: np.ndarray) -> tuple[int, float]:
    """Compute overlap height (pixels) and match score using Canny edges and template matching."""
    prev_edges = cv2.Canny(prev_img, 60, 180)
    curr_edges = cv2.Canny(curr_img, 60, 180)
    template_h = int(curr_edges.shape[0] * 0.2)
    template = curr_edges[:template_h, :]
    result = cv2.matchTemplate(prev_edges, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    overlap_h = prev_edges.shape[0] - max_loc[1]
    return overlap_h, float(max_val)

def stitch_screenshots(
    screenshot_paths: List[Path],
    output_path: Path,
    write_output: bool = True,
    scroll_region: CropRegion = SCROLLABLE_REGION,
) -> Dict[str, object]:
    """Stitch scroll-ordered screenshots into one image; header/footer from first/last frame."""
    assert len(screenshot_paths) >= 1, "need at least 1 screenshot"
    n = len(screenshot_paths)

    first_img_raw = cv2.imdecode(np.frombuffer(screenshot_paths[0].read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
    last_img_raw = cv2.imdecode(np.frombuffer(screenshot_paths[-1].read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
    header = first_img_raw[:scroll_region.y, :scroll_region.w]
    bottom_y = scroll_region.y + scroll_region.h
    footer = last_img_raw[bottom_y:, :scroll_region.w]

    images = [
        _load_and_crop(p, scroll_region)
        for p in screenshot_paths
    ]

    if n == 1:
        if write_output:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(output_path), np.vstack([header, images[0], footer]))
        return {"pair_overlaps": [], "match_scores": [], "output_path": str(output_path) if write_output else ""}

    overlaps: List[int] = []
    scores: List[float] = []
    for idx in range(n - 1):
        overlap_h, score = _estimate_overlap(images[idx], images[idx + 1])
        if score < 0.4 and overlaps:
            overlap_h = overlaps[-1]
        overlaps.append(overlap_h)
        scores.append(score)

    if write_output:
        chat_parts = [images[0]] + [
            images[i][overlaps[i - 1]:, :] for i in range(1, n)
        ]
        stitched_chat = np.vstack(chat_parts)
        final_image = np.vstack([header, stitched_chat, footer])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(output_path), final_image)

    return {
        "pair_overlaps": overlaps,
        "match_scores": scores,
        "output_path": str(output_path) if write_output else ""
    }