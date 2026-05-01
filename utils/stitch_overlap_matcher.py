"""Candidate matcher for vertical chat screenshot overlap."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


_cv2_mod = None


@dataclass(frozen=True)
class OverlapMatch:
    overlap: int
    cost: float
    score: float
    seam_corr: float
    refine_cost: float
    source: str
    reliable: bool


def _cv2():
    global _cv2_mod
    if _cv2_mod is None:
        import cv2 as _m

        _cv2_mod = _m
    return _cv2_mod


def to_gray(panel: np.ndarray) -> np.ndarray:
    cv2 = _cv2()
    return cv2.cvtColor(panel, cv2.COLOR_RGB2GRAY)


def to_edges(gray: np.ndarray) -> np.ndarray:
    cv2 = _cv2()
    grad_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    grad = cv2.convertScaleAbs(cv2.magnitude(grad_x, grad_y))
    edges = cv2.Canny(gray, 60, 180)
    return cv2.addWeighted(grad, 0.65, edges, 0.35, 0.0)


def center_band(img: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    x0 = int(w * 0.08)
    x1 = int(w * 0.92)
    if x1 <= x0 + 32:
        x0, x1 = 0, w
    return img[:h, x0:x1]


def seam_correlation(prev_feat: np.ndarray, next_feat: np.ndarray, overlap: int) -> float:
    if overlap <= 1:
        return -1.0
    a = center_band(prev_feat)[-overlap:].astype(np.float32)
    b = center_band(next_feat)[:overlap].astype(np.float32)
    if a.shape != b.shape or a.size == 0:
        return -1.0
    a = a - float(a.mean())
    b = b - float(b.mean())
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom < 1e-6:
        return -1.0
    return float(np.sum(a * b) / denom)


def refine_overlap(
    prev_feat: np.ndarray,
    next_feat: np.ndarray,
    coarse_overlap: int,
    min_overlap: int,
    max_overlap: int,
) -> tuple[int, float]:
    prev_band = center_band(prev_feat)
    next_band = center_band(next_feat)
    low = max(min_overlap, coarse_overlap - 48)
    high = min(max_overlap, coarse_overlap + 48)
    best_overlap = coarse_overlap
    best_cost = float("inf")
    for overlap in range(low, high + 1):
        a = prev_band[-overlap:]
        b = next_band[:overlap]
        if a.shape != b.shape:
            continue
        cost = float(np.mean(np.abs(a.astype(np.int16) - b.astype(np.int16))))
        if cost < best_cost:
            best_cost = cost
            best_overlap = overlap
    return best_overlap, best_cost


def make_candidate(
    overlap: int,
    score: float,
    refine_cost: float,
    seam_corr: float,
    source: str,
    overlap_hint: int | None,
    h_min: int,
) -> OverlapMatch:
    jump = abs(overlap - overlap_hint) / float(h_min) if overlap_hint is not None else 0.0
    cost = refine_cost - score * 65.0 - max(seam_corr, -0.25) * 35.0 + jump * 45.0
    reliable = score >= 0.42 or seam_corr >= 0.18 or refine_cost <= 18.0
    return OverlapMatch(overlap, cost, score, seam_corr, refine_cost, source, reliable)


def template_candidates(
    prev_feat: np.ndarray,
    next_feat: np.ndarray,
    overlap_hint: int | None,
    source: str,
) -> list[OverlapMatch]:
    cv2 = _cv2()
    h_prev, h_next = prev_feat.shape[:2]
    h_min = min(h_prev, h_next)
    min_overlap = max(30, int(h_min * 0.08))
    max_overlap = min(h_min - 2, int(h_min * 0.95))
    if max_overlap < min_overlap:
        return []
    heights = sorted({max(36, int(h_min * r)) for r in (0.14, 0.22, 0.30)})
    out: list[OverlapMatch] = []
    for template_h in heights:
        if template_h >= h_min:
            continue
        template = next_feat[:template_h]
        for ratio in (0.65, 0.85, 1.0):
            search_h = min(h_prev, max(template_h + 64, int(h_prev * ratio)))
            if search_h <= template_h:
                continue
            search = prev_feat[-search_h:]
            width = min(search.shape[1], template.shape[1])
            result = cv2.matchTemplate(search[:, :width], template[:, :width], cv2.TM_CCOEFF_NORMED)
            _, score, _, loc = cv2.minMaxLoc(result)
            coarse_start = h_prev - search_h + loc[1]
            coarse_overlap = h_prev - coarse_start
            if coarse_overlap < min_overlap or coarse_overlap > max_overlap:
                continue
            overlap, refine_cost = refine_overlap(prev_feat, next_feat, coarse_overlap, min_overlap, max_overlap)
            seam_corr = seam_correlation(prev_feat, next_feat, overlap)
            out.append(make_candidate(overlap, float(score), refine_cost, seam_corr, source, overlap_hint, h_min))
    return out


def profile_candidate(
    prev_gray: np.ndarray,
    next_gray: np.ndarray,
    overlap_hint: int | None,
) -> OverlapMatch | None:
    h_min = min(prev_gray.shape[0], next_gray.shape[0])
    min_overlap = max(30, int(h_min * 0.08))
    max_overlap = min(h_min - 2, int(h_min * 0.95))
    if max_overlap < min_overlap:
        return None
    prev_profile = np.mean(np.abs(255.0 - center_band(prev_gray).astype(np.float32)), axis=1)
    next_profile = np.mean(np.abs(255.0 - center_band(next_gray).astype(np.float32)), axis=1)
    best_overlap = min_overlap
    best_corr = -1.0
    step = max(1, (max_overlap - min_overlap) // 160)
    for overlap in range(min_overlap, max_overlap + 1, step):
        a = prev_profile[-overlap:] - float(prev_profile[-overlap:].mean())
        b = next_profile[:overlap] - float(next_profile[:overlap].mean())
        denom = float(np.linalg.norm(a) * np.linalg.norm(b))
        corr = -1.0 if denom < 1e-6 else float(np.sum(a * b) / denom)
        if corr > best_corr:
            best_corr = corr
            best_overlap = overlap
    overlap, refine_cost = refine_overlap(prev_gray, next_gray, best_overlap, min_overlap, max_overlap)
    seam_corr = seam_correlation(prev_gray, next_gray, overlap)
    return make_candidate(overlap, max(best_corr, 0.0), refine_cost, seam_corr, "profile", overlap_hint, h_min)


def estimate_overlap_match(
    prev_body: np.ndarray,
    next_body: np.ndarray,
    overlap_hint: int | None = None,
) -> OverlapMatch:
    h_min = min(prev_body.shape[0], next_body.shape[0])
    if h_min < 48:
        return OverlapMatch(0, float("inf"), 0.0, -1.0, float("inf"), "none", False)
    width = min(prev_body.shape[1], next_body.shape[1])
    prev_body = prev_body[:, :width]
    next_body = next_body[:, :width]
    prev_gray = to_gray(prev_body)
    next_gray = to_gray(next_body)
    candidates = template_candidates(prev_gray, next_gray, overlap_hint, "gray")
    candidates.extend(template_candidates(to_edges(prev_gray), to_edges(next_gray), overlap_hint, "edge"))
    profile = profile_candidate(prev_gray, next_gray, overlap_hint)
    if profile is not None:
        candidates.append(profile)
    if not candidates:
        return OverlapMatch(0, float("inf"), 0.0, -1.0, float("inf"), "none", False)
    reliable = [item for item in candidates if item.reliable]
    pool = reliable or candidates
    return min(pool, key=lambda item: item.cost)
