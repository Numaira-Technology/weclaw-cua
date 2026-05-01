"""Stitch chat-panel crops vertically for vision models.

Uses overlap estimation between consecutive frames (not naive vstack) so repeated
composer/footer and duplicate PageUp frames do not tile infinitely.

On Retina macOS, screenshot pixel size often differs from Quartz logical bounds;
always derive CropRegion from the actual PIL image size.

Stitched images sent to the VLM are saved under debug_outputs/chat_stitch/ (see utils.chat_stitch_debug). Set WECLAW_DEBUG_STITCH_DIR to use a different directory.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np
from PIL import Image

from utils.stitch_overlap import body_lo, estimate_vertical_overlap_rows, strip_body_for_match


@dataclass(frozen=True)
class CropRegion:
    x: int
    y: int
    w: int
    h: int


def scroll_region_from_image_size(img_w: int, img_h: int) -> CropRegion:
    assert img_w > 80 and img_h > 80
    y0 = max(1, min(50, img_h // 16))
    y1 = max(y0 + 200, img_h - max(90, img_h // 8))
    return CropRegion(
        x=int(img_w * 0.30),
        y=y0,
        w=min(int(img_w * 0.69), img_w - int(img_w * 0.30)),
        h=y1 - y0,
    )


def _apply_crop(rgb: np.ndarray, region: CropRegion) -> np.ndarray:
    H, W, _ = rgb.shape
    x2 = min(region.x + region.w, W)
    y2 = min(region.y + region.h, H)
    assert region.x < x2 and region.y < y2
    return np.asarray(rgb[region.y:y2, region.x:x2])


def stitch_screenshots(
    images: List[Image.Image],
    scroll_region: CropRegion | None = None,
    match_top_trim: int = 48,
    match_bottom_trim: int = 130,
    duplicate_mse: float = 80.0,
    bad_match_mse: float = 2200.0,
) -> Image.Image | None:
    """Crop each image to the chat panel, then merge by removing inter-frame gap."""
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

    panorama = cropped[0]
    skips = 0

    for i in range(1, len(cropped)):
        prev_p = cropped[i - 1]
        next_p = cropped[i]

        if prev_p.shape == next_p.shape:
            mean_diff = float(
                np.mean(
                    np.abs(
                        prev_p.astype(np.float32) - next_p.astype(np.float32),
                    )
                )
            )
        else:
            mean_diff = 9999.0
        if mean_diff < 1.2:
            print(f"[INFO] stitch: frame {i + 1} nearly identical to {i}; skip.")
            skips += 1
            continue

        ov_b, mse = estimate_vertical_overlap_rows(
            prev_p,
            next_p,
            match_top_trim,
            match_bottom_trim,
        )
        Hn = next_p.shape[0]
        sa = strip_body_for_match(prev_p, match_top_trim, match_bottom_trim).shape[0]
        sb = strip_body_for_match(next_p, match_top_trim, match_bottom_trim).shape[0]

        if mse <= duplicate_mse and ov_b >= min(sa, sb) * 0.82:
            print(f"[INFO] stitch: frame {i + 1} full duplicate (mse={mse:.1f}); skip.")
            skips += 1
            continue

        if mse > bad_match_mse or ov_b <= 0:
            cut = max(int(Hn * 0.12), 80, min(Hn // 4, 200))
            print(f"[WARN] stitch: weak overlap (mse={mse:.1f}); append from row {cut}.")
            append_part = next_p[cut:]
        else:
            cut = body_lo(Hn, match_top_trim) + ov_b
            cut = max(0, min(Hn - 8, cut))
            append_part = next_p[cut:]
            print(f"[+] stitch: overlap ~{cut}px (body ov={ov_b}, mse={mse:.1f}).")

        if append_part.shape[0] < 12:
            continue
        panorama = np.vstack([panorama, append_part])

    print(f"[+] Stitched {len(cropped)} frames -> one strip ({skips} skipped); rows={panorama.shape[0]}.")
    return Image.fromarray(panorama)
