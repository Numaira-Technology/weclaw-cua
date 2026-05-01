"""Stitch chat-panel crops vertically for vision models.

Uses overlap estimation between consecutive frames (not naive vstack) so repeated
composer/footer and duplicate PageUp frames do not tile infinitely.

On Retina macOS, screenshot pixel size often differs from Quartz logical bounds;
always derive CropRegion from the actual PIL image size.

Stitched images sent to the VLM are saved under debug_outputs/chat_stitch/ (see utils.chat_stitch_debug). Set WECLAW_DEBUG_STITCH_DIR to use a different directory.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import List

import numpy as np
from PIL import Image

from utils.stitch_overlap import body_hi, body_lo, estimate_vertical_overlap_match, strip_body_for_match


@dataclass(frozen=True)
class CropRegion:
    x: int
    y: int
    w: int
    h: int


def scroll_region_from_image_size(img_w: int, img_h: int) -> CropRegion:
    assert img_w > 80 and img_h > 80
    y0 = 0
    y1 = max(y0 + 200, img_h - max(90, img_h // 8))
    x0 = int(img_w * 0.31)
    x1 = int(img_w * 0.95)
    return CropRegion(
        x=x0,
        y=y0,
        w=max(80, min(x1, img_w) - x0),
        h=y1 - y0,
    )


def _apply_crop(rgb: np.ndarray, region: CropRegion) -> np.ndarray:
    H, W, _ = rgb.shape
    x2 = min(region.x + region.w, W)
    y2 = min(region.y + region.h, H)
    assert region.x < x2 and region.y < y2
    return np.asarray(rgb[region.y:y2, region.x:x2])


def _dump_cropped_frames(cropped: list[np.ndarray]) -> None:
    out_dir = os.environ.get("WECLAW_DEBUG_STITCH_FRAMES_DIR", "").strip()
    if not out_dir:
        return
    path = Path(out_dir)
    path.mkdir(parents=True, exist_ok=True)
    for idx, frame in enumerate(cropped):
        Image.fromarray(frame).save(path / f"frame_{idx:03d}.png")
    print(f"[DEBUG] Chat stitch cropped frames saved: {path}")


def _frames_nearly_identical(
    prev_panel: np.ndarray,
    next_panel: np.ndarray,
    top_trim: int,
    bottom_trim: int,
) -> bool:
    if prev_panel.shape != next_panel.shape:
        return False
    prev_body = strip_body_for_match(prev_panel, top_trim, bottom_trim)
    next_body = strip_body_for_match(next_panel, top_trim, bottom_trim)
    height = min(prev_body.shape[0], next_body.shape[0])
    width = min(prev_body.shape[1], next_body.shape[1])
    if height < 40 or width < 40:
        return False
    diff = np.abs(
        prev_body[:height, :width].astype(np.int16)
        - next_body[:height, :width].astype(np.int16)
    )
    changed = float(np.count_nonzero(diff > 6)) / float(diff.size)
    return changed < 0.003 and float(diff.mean()) < 0.8


def _stitch_with_scroll_stitch(
    cropped: list[np.ndarray],
    match_top_trim: int,
    match_bottom_trim: int,
) -> Image.Image | None:
    import importlib

    stitcher = importlib.import_module("stitcher")
    StitchParams = stitcher.StitchParams
    stitch_images = stitcher.stitch_images

    if len(cropped) == 1:
        return Image.fromarray(cropped[0])

    bgr_images = [frame[:, :, ::-1].copy() for frame in cropped]
    panel_w = bgr_images[0].shape[1]
    x_margin = max(8, min(80, panel_w // 28))
    template_height = max(100, min(360, (bgr_images[0].shape[0] - match_top_trim - match_bottom_trim) // 4))
    params = StitchParams(
        top_crop=max(0, int(match_top_trim)),
        bottom_crop=max(0, int(match_bottom_trim)),
        x_margin=x_margin,
        template_height=template_height,
        threshold=0.52,
    )
    stitched_bgr, infos = stitch_images(bgr_images, params)
    for idx, info in enumerate(infos, start=1):
        print(
            f"[INFO] scroll_stitch pair={idx} conf={info.confidence:.3f} "
            f"consensus={info.consensus:.3f} offset={info.offset}px "
            f"overlap={info.overlap_height}px mode={info.mode}"
        )
    return Image.fromarray(stitched_bgr[:, :, ::-1])


def stitch_screenshots(
    images: List[Image.Image],
    scroll_region: CropRegion | None = None,
    match_top_trim: int = 88,
    match_bottom_trim: int = 130,
    duplicate_mse: float = 80.0,
    bad_match_mse: float = 2200.0,
) -> Image.Image | None:
    """Crop each image to the chat panel, then merge by removing inter-frame gap."""
    _ = duplicate_mse, bad_match_mse
    if not images:
        print("[WARN] No images provided to stitch.")
        return None

    first = np.array(images[0].convert("RGB"))
    if scroll_region is None:
        H, W = first.shape[0], first.shape[1]
        scroll_region = scroll_region_from_image_size(W, H)
    else:
        H, W = first.shape[0], first.shape[1]
        max_x = scroll_region.x + scroll_region.w
        max_y = scroll_region.y + scroll_region.h
        if max_x > W or max_y > H or scroll_region.x < 0 or scroll_region.y < 0:
            scroll_region = scroll_region_from_image_size(W, H)
            print(
                "[WARN] scroll_region mismatched screenshot size; "
                "using fractions of image pixels instead."
            )

    cropped: list[np.ndarray] = []
    for image in images:
        rgb = np.array(image.convert("RGB"))
        cropped.append(_apply_crop(rgb, scroll_region))
    _dump_cropped_frames(cropped)

    backend = os.environ.get("WECLAW_STITCH_BACKEND", "").strip().lower()
    if backend in ("", "scroll_stitch"):
        result = _stitch_with_scroll_stitch(
            cropped=cropped,
            match_top_trim=match_top_trim,
            match_bottom_trim=match_bottom_trim,
        )
        if result is not None:
            print("[+] Stitched with scroll_stitch backend.")
            return result

    panorama = cropped[0]
    skips = 0
    prev_overlap: int | None = None

    for i in range(1, len(cropped)):
        prev_p = cropped[i - 1]
        next_p = cropped[i]

        if _frames_nearly_identical(prev_p, next_p, match_top_trim, match_bottom_trim):
            print(f"[INFO] stitch: frame {i + 1} nearly identical to {i}; skip.")
            skips += 1
            continue

        match = estimate_vertical_overlap_match(
            prev_p,
            next_p,
            match_top_trim,
            match_bottom_trim,
            overlap_hint=prev_overlap,
        )
        Hn = next_p.shape[0]
        body_start = body_lo(Hn, match_top_trim)
        body_end = body_hi(Hn, match_top_trim, match_bottom_trim)
        body_h = body_end - body_start
        if match.overlap <= 0:
            overlap = 0
            reliable = False
        elif match.reliable:
            overlap = match.overlap
            reliable = True
        elif prev_overlap is not None:
            overlap = min(prev_overlap, body_h - 1)
            reliable = False
        else:
            overlap = min(match.overlap, max(0, int(body_h * 0.45)))
            reliable = False

        cut = body_start + overlap + (Hn - body_end)
        cut = max(body_start, min(Hn - 1, cut))
        append_part = next_p[cut:]
        prev_overlap = overlap if overlap > 0 else prev_overlap
        level = "+" if reliable else "WARN"
        print(
            f"[{level}] stitch: cut={cut}px, body_ov={overlap}, "
            f"score={match.score:.3f}, seam={match.seam_corr:.3f}, "
            f"cost={match.refine_cost:.1f}, source={match.source}."
        )
        if append_part.shape[0] < 12:
            print(f"[INFO] stitch: frame {i + 1} contributes {append_part.shape[0]} rows.")
        panorama = np.vstack([panorama, append_part])

    print(f"[+] Stitched {len(cropped)} frames -> one strip ({skips} skipped); rows={panorama.shape[0]}.")
    return Image.fromarray(panorama)
