"""Vertical overlap estimation between consecutive chat-panel crops."""

from __future__ import annotations

import numpy as np


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


def estimate_vertical_overlap_rows(
    prev_panel: np.ndarray,
    next_panel: np.ndarray,
    top_trim: int,
    bottom_trim: int,
) -> tuple[int, float]:
    a = strip_body_for_match(prev_panel, top_trim, bottom_trim)
    b = strip_body_for_match(next_panel, top_trim, bottom_trim)
    Ha, Wa, _ = a.shape
    Hb, Wb, _ = b.shape
    w = min(Wa, Wb)
    a = a[:, :w]
    b = b[:, :w]
    wl = int(w * 0.12)
    wr = int(w * 0.88)
    if wr <= wl + 32:
        wl, wr = 0, w
    a = a[:, wl:wr]
    b = b[:, wl:wr]
    Ha = a.shape[0]

    ov_min = max(50, int(min(Ha, b.shape[0]) * 0.08))
    ov_max = min(Ha, b.shape[0]) - 30
    if ov_max < ov_min:
        return 0, float("inf")

    best_ov = ov_min
    best_mse = float("inf")
    coarse = max(4, (ov_max - ov_min) // 40)
    for ov in range(ov_min, ov_max + 1, coarse):
        mse = match_mse(a[Ha - ov : Ha], b[:ov])
        if mse < best_mse:
            best_mse = mse
            best_ov = ov

    lo = max(ov_min, best_ov - coarse)
    hi = min(ov_max, best_ov + coarse)
    for ov in range(lo, hi + 1):
        mse = match_mse(a[Ha - ov : Ha], b[:ov])
        if mse < best_mse:
            best_mse = mse
            best_ov = ov
    return best_ov, best_mse
