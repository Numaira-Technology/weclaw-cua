"""Public vertical overlap API for chat-panel screenshot stitching."""

from __future__ import annotations

import numpy as np

from utils.stitch_overlap_matcher import OverlapMatch, estimate_overlap_match


def strip_body_for_match(panel: np.ndarray, top_trim: int, bottom_trim: int) -> np.ndarray:
    H, _, _ = panel.shape
    lo = min(top_trim, H // 4)
    hi = max(lo + 80, H - bottom_trim)
    return panel[lo:hi]


def match_mse(a_bottom: np.ndarray, b_top: np.ndarray) -> float:
    assert a_bottom.shape == b_top.shape
    d = a_bottom.astype(np.float32) - b_top.astype(np.float32)
    return float(np.mean(d * d))


def body_lo(panel_h: int, top_trim: int) -> int:
    return min(top_trim, max(1, panel_h // 4))


def body_hi(panel_h: int, top_trim: int, bottom_trim: int) -> int:
    lo = body_lo(panel_h, top_trim)
    return min(panel_h, max(lo + 80, panel_h - bottom_trim))


def estimate_vertical_overlap_match(
    prev_panel: np.ndarray,
    next_panel: np.ndarray,
    top_trim: int,
    bottom_trim: int,
    overlap_hint: int | None = None,
) -> OverlapMatch:
    prev_body = strip_body_for_match(prev_panel, top_trim, bottom_trim)
    next_body = strip_body_for_match(next_panel, top_trim, bottom_trim)
    return estimate_overlap_match(prev_body, next_body, overlap_hint)


def estimate_vertical_overlap_rows(
    prev_panel: np.ndarray,
    next_panel: np.ndarray,
    top_trim: int,
    bottom_trim: int,
) -> tuple[int, float]:
    match = estimate_vertical_overlap_match(prev_panel, next_panel, top_trim, bottom_trim)
    return match.overlap, match.refine_cost
