"""将多张聊天截图拼接为一张长图。

核心算法（移植自 wechat-admin-bot-main/modules/whole_pic_generator.py）：
  1. Sobel + Canny 边缘增强
  2. 多尺度模板匹配估算相邻帧重叠量
  3. 逐像素精调 + seam 相关性校验
  4. 按重叠量垂直拼接

输入：有序的 PIL Image 列表（已裁切为聊天内容区域）
输出：拼接后的 PIL Image + 重叠/匹配元数据
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

_cv2_mod = None


def _cv2():
    """延迟加载 OpenCV：避免在 import 阶段 dlopen 失败时脚本无任何输出。

    若加载失败，抛出带修复提示的 RuntimeError。
    """
    global _cv2_mod
    if _cv2_mod is None:
        try:
            import cv2 as _m

            _cv2_mod = _m
        except Exception as e:
            raise RuntimeError(
                "无法加载 OpenCV (cv2)。常见原因：wheel 损坏、ffmpeg 动态库与系统不兼容。\n"
                "请尝试：\n"
                "  pip uninstall -y opencv-python opencv-python-headless\n"
                "  pip install --no-cache-dir opencv-python\n"
                f"原始错误: {e}"
            ) from e
    return _cv2_mod


# ── 工具函数 ──────────────────────────────────────────────

def _pil_to_bgr(img: Image.Image) -> np.ndarray:
    cv2 = _cv2()
    rgb = np.array(img.convert("RGB"))
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def _bgr_to_pil(arr: np.ndarray) -> Image.Image:
    cv2 = _cv2()
    rgb = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


def _enhance_for_match(img_bgr: np.ndarray) -> np.ndarray:
    """Sobel 梯度 + Canny 边缘，用于模板匹配。"""
    cv2 = _cv2()
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    grad_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    grad_mag = cv2.convertScaleAbs(cv2.magnitude(grad_x, grad_y))
    edges = cv2.Canny(gray, 60, 180)
    return cv2.addWeighted(grad_mag, 0.65, edges, 0.35, 0.0)


def _to_gray(img_bgr: np.ndarray) -> np.ndarray:
    cv2 = _cv2()
    return cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)


# ── 重叠估算 ──────────────────────────────────────────────

def _refine_overlap(
    prev_feat: np.ndarray, curr_feat: np.ndarray, coarse_overlap: int
) -> Tuple[int, float]:
    """在粗估重叠量 ±48px 范围内逐像素精调。"""
    height = min(prev_feat.shape[0], curr_feat.shape[0])
    width = min(prev_feat.shape[1], curr_feat.shape[1])
    x0 = int(width * 0.1)
    x1 = int(width * 0.9)
    if x1 <= x0:
        x0, x1 = 0, width

    low = max(30, coarse_overlap - 48)
    high = min(height - 1, coarse_overlap + 48)
    best_overlap = coarse_overlap
    best_cost = float("inf")
    for overlap in range(low, high + 1):
        prev_tail = prev_feat[-overlap:, x0:x1]
        curr_head = curr_feat[:overlap, x0:x1]
        if prev_tail.shape != curr_head.shape:
            continue
        cost = float(np.mean(np.abs(prev_tail.astype(np.int16) - curr_head.astype(np.int16))))
        if cost < best_cost:
            best_cost = cost
            best_overlap = overlap
    return best_overlap, best_cost


def _seam_correlation(
    prev_feat: np.ndarray, curr_feat: np.ndarray, overlap: int
) -> float:
    """重叠区域的归一化互相关（-1 ~ +1）。"""
    if overlap <= 1:
        return -1.0
    width = min(prev_feat.shape[1], curr_feat.shape[1])
    x0 = int(width * 0.1)
    x1 = int(width * 0.9)
    if x1 <= x0:
        x0, x1 = 0, width

    a = prev_feat[-overlap:, x0:x1].astype(np.float32)
    b = curr_feat[:overlap, x0:x1].astype(np.float32)
    if a.shape != b.shape or a.size == 0:
        return -1.0
    a = a - float(a.mean())
    b = b - float(b.mean())
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom < 1e-6:
        return -1.0
    return float(np.sum(a * b) / denom)


def _match_template_multi(
    prev_feat: np.ndarray, curr_feat: np.ndarray,
    overlap_hint: Optional[int],
) -> list[dict]:
    """在单种特征图上做多尺度模板匹配，返回候选列表。"""
    cv2 = _cv2()
    h_prev = prev_feat.shape[0]
    h_curr = curr_feat.shape[0]
    h_min = min(h_prev, h_curr)

    template_heights = sorted({
        max(80, int(h_curr * 0.16)),
        max(80, int(h_curr * 0.22)),
        max(80, int(h_curr * 0.30)),
    })
    candidates: list[dict] = []

    def _collect(search_ratios: list[float]) -> None:
        for template_h in template_heights:
            template = curr_feat[:template_h, :]
            for ratio in search_ratios:
                search_h = max(template_h + 100, int(h_prev * ratio))
                search_h = min(search_h, h_prev)
                if search_h <= template_h:
                    continue
                search_region = prev_feat[-search_h:, :]
                if template.shape[1] != search_region.shape[1]:
                    w = min(template.shape[1], search_region.shape[1])
                    template_cropped = template[:, :w]
                    search_cropped = search_region[:, :w]
                else:
                    template_cropped = template
                    search_cropped = search_region
                result = cv2.matchTemplate(search_cropped, template_cropped, cv2.TM_CCOEFF_NORMED)
                _, score, _, max_loc = cv2.minMaxLoc(result)
                coarse_start = h_prev - search_h + max_loc[1]
                coarse_overlap = h_prev - coarse_start
                refined_overlap, refine_cost = _refine_overlap(
                    prev_feat, curr_feat, coarse_overlap
                )
                refined_overlap = max(0, min(refined_overlap, h_min - 1))
                seam_corr = _seam_correlation(prev_feat, curr_feat, refined_overlap)
                jump_penalty = (
                    abs(refined_overlap - overlap_hint) / float(h_min)
                    if overlap_hint is not None else 0.0
                )
                candidates.append({
                    "overlap": refined_overlap,
                    "score": float(score),
                    "refine_cost": float(refine_cost),
                    "seam_corr": seam_corr,
                    "jump_penalty": jump_penalty,
                })

    _collect([0.70, 0.85])
    best_primary = max((c["score"] for c in candidates), default=float("-inf"))
    if best_primary < 0.45:
        _collect([0.60, 1.0])

    return candidates


def estimate_pair_overlap(
    prev_img: np.ndarray, curr_img: np.ndarray,
    overlap_hint: Optional[int] = None,
) -> Dict[str, float | int]:
    """估算两帧之间的竖直重叠量。

    同时使用边缘增强和灰度两种特征做模板匹配，取最佳结果。

    返回 dict:
      overlap_h, curr_h, new_h, score, seam_corr, refine_cost
    """
    h_prev = prev_img.shape[0]
    h_curr = curr_img.shape[0]
    h_min = min(h_prev, h_curr)
    min_overlap = max(1, int(h_min * 0.08))
    max_overlap = min(h_min - 1, int(h_min * 0.95))

    prev_edge = _enhance_for_match(prev_img)
    curr_edge = _enhance_for_match(curr_img)
    prev_gray = _to_gray(prev_img)
    curr_gray = _to_gray(curr_img)

    candidates = _match_template_multi(prev_edge, curr_edge, overlap_hint)
    candidates += _match_template_multi(prev_gray, curr_gray, overlap_hint)

    if not candidates:
        return {"overlap_h": 0, "curr_h": h_curr, "new_h": h_curr,
                "score": 0.0, "seam_corr": -1.0, "refine_cost": 999.0}

    pool = [c for c in candidates
            if 0.08 <= c["overlap"] / h_min <= 0.95
            and (c["score"] >= 0.45 or c["seam_corr"] >= 0.20)]
    if not pool:
        pool = [c for c in candidates if 0.08 <= c["overlap"] / h_min <= 0.95]
    if not pool:
        pool = candidates

    best = max(pool, key=lambda c: (c["score"], c["seam_corr"], -c["jump_penalty"], -c["refine_cost"]))
    overlap = int(best["overlap"])
    overlap = min(max(overlap, min_overlap), max_overlap)
    new_h = max(0, h_curr - overlap)
    return {
        "overlap_h": overlap, "curr_h": h_curr, "new_h": new_h,
        "score": float(best["score"]), "seam_corr": float(best["seam_corr"]),
        "refine_cost": float(best["refine_cost"]),
    }


# ── 拼接 ──────────────────────────────────────────────────

def _compose_long_image(images: List[np.ndarray], overlaps: List[int]) -> np.ndarray:
    """按重叠量竖直拼接多帧。"""
    parts: list[np.ndarray] = [images[0]]
    for idx in range(1, len(images)):
        overlap_h = overlaps[idx - 1]
        parts.append(images[idx][overlap_h:, :] if overlap_h > 0 else images[idx])
    return np.vstack(parts)


def stitch_screenshots(
    images: List[Image.Image],
    output_path: Optional[str] = None,
) -> Dict[str, object]:
    """将多张 PIL Image 拼接为一张长图。

    返回 dict:
      long_image     — 拼接后的 PIL Image
      pair_overlaps  — 每对相邻帧的重叠高度
      match_scores   — 每对的匹配得分
      output_path    — 如果提供了路径则保存并返回
    """
    bgr_images = [_pil_to_bgr(img) for img in images]

    if len(bgr_images) == 1:
        result_img = _bgr_to_pil(bgr_images[0])
        if output_path:
            result_img.save(output_path)
        return {"long_image": result_img, "pair_overlaps": [], "match_scores": [],
                "output_path": output_path or ""}

    overlaps: list[int] = []
    scores: list[float] = []
    prev_hint: Optional[int] = None

    for idx in range(len(bgr_images) - 1):
        metrics = estimate_pair_overlap(bgr_images[idx], bgr_images[idx + 1],
                                        overlap_hint=prev_hint)
        overlap_h = int(metrics["overlap_h"])
        score = float(metrics["score"])

        if prev_hint is not None:
            jump_limit = max(60, int(min(bgr_images[idx].shape[0],
                                         bgr_images[idx + 1].shape[0]) * 0.35))
            if abs(overlap_h - prev_hint) > jump_limit and score < 0.62:
                overlap_h = prev_hint

        overlaps.append(overlap_h)
        scores.append(score)
        prev_hint = overlap_h

    merged = _compose_long_image(bgr_images, overlaps)
    result_img = _bgr_to_pil(merged)

    if output_path:
        result_img.save(output_path)

    return {
        "long_image": result_img,
        "pair_overlaps": overlaps,
        "match_scores": scores,
        "output_path": output_path or "",
    }
