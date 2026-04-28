"""WeChat sidebar 视觉检测：会话行、未读 badge、聊天名称。

策略分两层：
  Layer 1 — 颜色/形状规则检测红色 badge 和 muted 小红点
  Layer 2 — 仅在需要时对 badge 数字和 chat name 做局部 OCR（macOS Vision，无 OpenRouter）

**核心原则**：所有检测均在 row-local 坐标系中完成。
每个 row 独立 crop → 独立检测 → badge/name 不会跨 row 污染。

所有坐标和尺寸均为 Retina 物理像素（截图原始分辨率）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image

from platform_mac.ocr import OCRResult, ocr_image, prepare_image_for_vision_ocr
from shared.sidebar_ui_chrome import is_sidebar_ui_chrome_label


# ── 数据结构 ──────────────────────────────────────────────

@dataclass
class Rect:
    x: int
    y: int
    width: int
    height: int

    @property
    def x2(self) -> int:
        return self.x + self.width

    @property
    def y2(self) -> int:
        return self.y + self.height

    @property
    def center_x(self) -> int:
        return self.x + self.width // 2

    @property
    def center_y(self) -> int:
        return self.y + self.height // 2

    def crop_from(self, img: Image.Image) -> Image.Image:
        return img.crop((self.x, self.y, self.x2, self.y2))


@dataclass
class RowRegions:
    """Row 内的固定子区域（坐标相对于 row_img 左上角）。"""
    badge: Rect
    name: Rect
    preview: Rect


@dataclass
class ChatInfo:
    name: str
    unread_count: int | None     # None=无未读, -1=muted 红点, 正数=未读数
    badge_type: str              # "count" | "dot" | "none"
    source: str = "vision_mac"
    confidence: float = 0.0
    row_rect: Optional[Rect] = None     # 行在窗口截图中的绝对像素坐标
    window_rect: Optional[Rect] = None  # 微信窗口在屏幕上的逻辑坐标
    name_ocr_raw: str = ""               # 名称子区域 OCR 原文（调试用，含置信度）


# ── 布局常量（Retina 2x，可调） ──────────────────────────

SIDEBAR_WIDTH_RATIO_FALLBACK = 0.22   # 动态检测失败时的兜底比例
TITLEBAR_HEIGHT_RATIO = 0.06

SEARCH_TOOLBAR_HEIGHT = 30
ROW_HEIGHT_DEFAULT = 136

# 动态检测：sidebar 宽度的搜索范围（占窗口宽度比例）
SIDEBAR_SEARCH_MIN = 0.12
SIDEBAR_SEARCH_MAX = 0.45

# ── Row 子区域比例（相对 row 宽高）──────────────────────
# Badge 出现在 avatar 右上角（行左侧），只扫上半部分防止跨行
ROW_BADGE_X0 = 0.08
ROW_BADGE_X1 = 0.52
ROW_BADGE_Y0 = 0.0
ROW_BADGE_Y1 = 0.55

# 聊天名称在 avatar 右侧、行上半部分
ROW_NAME_X0 = 0.19
ROW_NAME_X1 = 0.72
ROW_NAME_Y0 = 0.03
ROW_NAME_Y1 = 0.48

# 预览文本在名称下方
ROW_PREVIEW_X0 = 0.19
ROW_PREVIEW_X1 = 0.85
ROW_PREVIEW_Y0 = 0.48
ROW_PREVIEW_Y1 = 0.88

ROW_NAME_WIDE_X0 = 0.11
ROW_NAME_WIDE_X1 = 0.93
ROW_NAME_WIDE_Y0 = 0.0
ROW_NAME_WIDE_Y1 = 0.66

# ── Badge 检测阈值 ───────────────────────────────────────

RED_R_MIN = 185
RED_G_MAX = 130
RED_B_MAX = 130
RED_LOOSE_R_MIN = 175
RED_LOOSE_DIFF = 55

BADGE_PIXEL_MIN = 28
DOT_MAX_DIMENSION = 28
BADGE_FILL_RATIO = 0.08
BADGE_OCR_MIN_SIZE = 48

# badge 中心 y 占行高比例的最大值，超过此值视为跨行污染
BADGE_CENTER_Y_MAX_RATIO = 0.60


# ── 1. Row 子区域计算 ────────────────────────────────────

def compute_row_subregions(w: int, h: int) -> RowRegions:
    """根据行的像素宽高计算三个子区域矩形。"""
    def _r(x0r: float, y0r: float, x1r: float, y1r: float) -> Rect:
        x0, y0, x1, y1 = int(w * x0r), int(h * y0r), int(w * x1r), int(h * y1r)
        return Rect(x0, y0, max(x1 - x0, 1), max(y1 - y0, 1))

    return RowRegions(
        badge=_r(ROW_BADGE_X0, ROW_BADGE_Y0, ROW_BADGE_X1, ROW_BADGE_Y1),
        name=_r(ROW_NAME_X0, ROW_NAME_Y0, ROW_NAME_X1, ROW_NAME_Y1),
        preview=_r(ROW_PREVIEW_X0, ROW_PREVIEW_Y0, ROW_PREVIEW_X1, ROW_PREVIEW_Y1),
    )


# ── 2. sidebar 区域检测（动态 + 兜底）──────────────────────

def _detect_sidebar_divider_x(img: Image.Image) -> Optional[int]:
    """通过竖直分割线的颜色突变自动定位 sidebar 右边界。

    算法：
      1. 取窗口中部一条水平带（30%~70% 高度），垂直平均消除内容噪声
      2. 计算列间亮度梯度
      3. 在 [SIDEBAR_SEARCH_MIN, SIDEBAR_SEARCH_MAX] 范围内找最强竖直边
      4. 如果边缘强度不足（< 中位数×3 或 < 2.0）则返回 None
    """
    arr = np.array(img)[:, :, :3].astype(np.float32)
    h, w, _ = arr.shape

    band_y0 = int(h * 0.30)
    band_y1 = int(h * 0.70)
    band = arr[band_y0:band_y1, :, :]

    col_avg = band.mean(axis=0)  # shape (w, 3)

    brightness = col_avg[:, 0] * 0.299 + col_avg[:, 1] * 0.587 + col_avg[:, 2] * 0.114
    gradient = np.abs(np.diff(brightness))

    x_start = int(w * SIDEBAR_SEARCH_MIN)
    x_end = int(w * SIDEBAR_SEARCH_MAX)
    search_grad = gradient[x_start:x_end]

    if len(search_grad) == 0:
        return None

    peak_idx = int(np.argmax(search_grad))
    peak_val = float(search_grad[peak_idx])

    median_grad = float(np.median(search_grad))
    if peak_val < max(median_grad * 3, 2.0):
        return None

    return x_start + peak_idx + 1


def detect_sidebar_region(img: Image.Image,
                          titlebar_ratio: float = TITLEBAR_HEIGHT_RATIO) -> Rect:
    """从完整窗口截图中定位 sidebar 矩形。

    优先用视觉分析自动检测 sidebar 右边界（竖直分割线），
    检测失败时回退到固定比例。
    """
    w, h = img.size
    titlebar_h = int(h * titlebar_ratio)

    divider_x = _detect_sidebar_divider_x(img)
    if divider_x is not None:
        sidebar_w = divider_x
    else:
        sidebar_w = int(w * SIDEBAR_WIDTH_RATIO_FALLBACK)

    return Rect(0, titlebar_h, sidebar_w, h - titlebar_h)


# ── 3. 会话行检测 ────────────────────────────────────────

def detect_session_rows(sidebar_img: Image.Image,
                        row_height: int = ROW_HEIGHT_DEFAULT,
                        skip_top: int = SEARCH_TOOLBAR_HEIGHT) -> List[Rect]:
    """将 sidebar 按固定行高切分为互不重叠的会话行矩形列表。

    skip_top 跳过搜索框区域。返回从上到下排序、无重叠。
    """
    w, h = sidebar_img.size
    rows: List[Rect] = []
    y = skip_top
    while y + row_height <= h:
        rows.append(Rect(0, y, w, row_height))
        y += row_height
    if y < h - 40:
        rows.append(Rect(0, y, w, h - y))

    # 断言：行间不重叠
    for i in range(1, len(rows)):
        assert rows[i].y >= rows[i - 1].y2, (
            f"Row {i} overlaps with row {i-1}: "
            f"prev.y2={rows[i-1].y2}, curr.y={rows[i].y}"
        )

    return rows


# ── 4. 红色像素检测 ──────────────────────────────────────

def _red_mask(arr: np.ndarray) -> np.ndarray:
    """从 RGB/RGBA numpy 数组生成红色像素的布尔 mask。"""
    r = arr[:, :, 0].astype(np.int16)
    g = arr[:, :, 1].astype(np.int16)
    b = arr[:, :, 2].astype(np.int16)
    strict = (r > RED_R_MIN) & (g < RED_G_MAX) & (b < RED_B_MAX)
    loose = (r > RED_LOOSE_R_MIN) & ((r - g) > RED_LOOSE_DIFF) & ((r - b) > RED_LOOSE_DIFF)
    return strict | loose


def _find_best_cluster(mask: np.ndarray) -> Optional[tuple[Rect, int]]:
    """在红色 mask 中找到最密集的聚类，返回 (bbox, red_count) 或 None。"""
    ys, xs = np.where(mask)
    total = len(xs)
    if total < BADGE_PIXEL_MIN:
        return None

    col_counts = np.bincount(xs, minlength=mask.shape[1])
    peak_col = int(np.argmax(col_counts))

    left = peak_col
    while left > 0 and col_counts[left - 1] > 0:
        left -= 1
    right = peak_col
    while right < len(col_counts) - 1 and col_counts[right + 1] > 0:
        right += 1

    col_mask = (xs >= left) & (xs <= right)
    cluster_xs = xs[col_mask]
    cluster_ys = ys[col_mask]
    count = len(cluster_xs)

    if count < BADGE_PIXEL_MIN:
        return None

    bbox = Rect(
        int(cluster_xs.min()), int(cluster_ys.min()),
        int(cluster_xs.max() - cluster_xs.min()) + 1,
        int(cluster_ys.max() - cluster_ys.min()) + 1,
    )

    area = bbox.width * bbox.height
    if area > 0 and (count / area) < BADGE_FILL_RATIO:
        return None

    aspect = max(bbox.width, bbox.height) / max(min(bbox.width, bbox.height), 1)
    if aspect > 2.5:
        row_counts = np.bincount(cluster_ys - int(cluster_ys.min()),
                                 minlength=bbox.height)
        win = min(bbox.width, bbox.height)
        best_start, best_sum = 0, 0
        for start in range(len(row_counts) - win + 1):
            s = int(row_counts[start:start + win].sum())
            if s > best_sum:
                best_sum, best_start = s, start
        new_y = int(cluster_ys.min()) + best_start
        bbox = Rect(bbox.x, new_y, bbox.width, win)
        count = best_sum
        area = bbox.width * bbox.height
        if area > 0 and (count / area) < BADGE_FILL_RATIO:
            return None

    return bbox, count


# ── 5. 未读 badge 检测（row-local）───────────────────────

def detect_unread_badge(row_img: Image.Image) -> dict:
    """在 row_img 的 badge 子区域内检测未读 badge。

    只扫描 badge sub-region（行上部 55%，avatar 附近），
    不会触及行下部避免跨行污染。

    返回 dict:
      has_unread  — bool
      unread_count — int | None
      badge_type  — "count" | "dot" | "none"
      badge_rect  — Rect | None (在 row 坐标系中)
    """
    w, h = row_img.size
    regions = compute_row_subregions(w, h)
    br = regions.badge

    # 只在 badge sub-region 内搜索红色像素
    scan_region = row_img.crop((br.x, br.y, br.x2, br.y2))

    arr = np.array(scan_region)
    if arr.ndim == 3 and arr.shape[2] == 4:
        arr = arr[:, :, :3]

    mask = _red_mask(arr)
    result = _find_best_cluster(mask)
    if result is None:
        return _no_badge()

    bbox, red_count = result
    # scan_region 坐标 → row 坐标
    bbox_in_row = Rect(br.x + bbox.x, br.y + bbox.y, bbox.width, bbox.height)

    # 严格校验：badge 中心 y 必须在行上部，否则可能是下一行的内容泄漏
    if bbox_in_row.center_y > h * BADGE_CENTER_Y_MAX_RATIO:
        return _no_badge()

    max_dim = max(bbox.width, bbox.height)

    if max_dim <= DOT_MAX_DIMENSION and red_count < 200:
        return {
            "has_unread": True,
            "unread_count": -1,
            "badge_type": "dot",
            "badge_rect": bbox_in_row,
        }

    count = _ocr_badge_number(row_img, bbox_in_row)
    return {
        "has_unread": True,
        "unread_count": count if count is not None else 1,
        "badge_type": "count",
        "badge_rect": bbox_in_row,
    }


def _no_badge() -> dict:
    return {"has_unread": False, "unread_count": None, "badge_type": "none", "badge_rect": None}


def _ocr_badge_number(row_img: Image.Image, badge_rect: Rect) -> int | None:
    """对 badge 小区域做 OCR 提取数字（macOS Vision）。"""
    from PIL import ImageOps

    pad = 8
    w, h = row_img.size
    x1 = max(0, badge_rect.x - pad)
    y1 = max(0, badge_rect.y - pad)
    x2 = min(w, badge_rect.x2 + pad)
    y2 = min(h, badge_rect.y2 + pad)
    crop = row_img.crop((x1, y1, x2, y2)).convert("RGB")

    crop = ImageOps.invert(crop)

    cw, ch = crop.size
    if cw < BADGE_OCR_MIN_SIZE or ch < BADGE_OCR_MIN_SIZE:
        scale = max(BADGE_OCR_MIN_SIZE // max(cw, 1), BADGE_OCR_MIN_SIZE // max(ch, 1), 2)
        crop = crop.resize((cw * scale, ch * scale), Image.LANCZOS)

    results = ocr_image(crop, min_confidence=0.1)
    for r in results:
        txt = r.text.strip().replace(" ", "")
        cleaned = txt.replace("+", "").replace("＋", "")
        if cleaned.isascii() and cleaned.isdigit():
            return min(int(cleaned), 999)
        if txt in ("99+", "99＋"):
            return 99
    return None


# ── 6. 聊天名称提取（row-local）─────────────────────────

def _clean_chat_name(raw: str) -> str:
    """清理 OCR chat name：去除头尾的 avatar 首字母、标点噪声。"""
    import re
    s = raw.strip()
    s = re.sub(r'^[A-Z]\s+(?=[\u4e00-\u9fff])', '', s)
    s = re.sub(r'^([A-Z])(?=[^\x00-\x7f])', lambda m: '' if len(m.group(0)) == 1 else m.group(0), s)
    s = re.sub(r'\s+[A-Z]$', '', s)
    s = s.rstrip("、，。：；")
    return s.strip()


def _name_ocr_crops_for_row(row_img: Image.Image) -> List[Tuple[str, Image.Image]]:
    w, h = row_img.size
    regions = compute_row_subregions(w, h)
    nr = regions.name
    tight = row_img.crop((nr.x, nr.y, nr.x2, nr.y2))
    wx0 = int(w * ROW_NAME_WIDE_X0)
    wy0 = int(h * ROW_NAME_WIDE_Y0)
    wx1 = max(wx0 + 1, int(w * ROW_NAME_WIDE_X1))
    wy1 = max(wy0 + 1, int(h * ROW_NAME_WIDE_Y1))
    wide = row_img.crop((wx0, wy0, wx1, wy1))
    return [("name", tight), ("name_preview", wide)]


def _name_from_ocr_results(results: List[OCRResult]) -> str:
    ordered = sorted(results, key=lambda r: (r.pixel_y, r.x))
    for min_c in (0.2, 0.12, 0.05, 0.0):
        for r in ordered:
            if r.confidence < min_c:
                continue
            cleaned = _clean_chat_name(r.text)
            if _is_valid_chat_name(cleaned):
                return cleaned
    return ""


def _preview_from_ocr_results(results: List[OCRResult]) -> str:
    ordered = sorted(results, key=lambda r: (r.pixel_y, r.x))
    parts: List[str] = []
    for r in ordered:
        t = r.text.replace("\n", " ").strip()
        if t:
            parts.append(f"{t!r}@{r.confidence:.2f}")
    return " | ".join(parts)


def extract_chat_name_with_preview(
    row_img: Image.Image,
    *,
    include_preview: bool = True,
    max_preview_chars: int = 400,
) -> tuple[str, str]:
    chunks: List[str] = []
    chosen = ""
    for tag, crop in _name_ocr_crops_for_row(row_img):
        prepared = prepare_image_for_vision_ocr(crop)
        results = ocr_image(prepared, min_confidence=0.0)
        if include_preview and results:
            chunks.append(f"{tag}: " + _preview_from_ocr_results(results))
        if not chosen:
            chosen = _name_from_ocr_results(results)
    preview_out = " ; ".join(chunks)
    if len(preview_out) > max_preview_chars:
        preview_out = preview_out[: max_preview_chars - 3] + "..."
    return chosen, preview_out


def extract_chat_name(row_img: Image.Image) -> str:
    n, _ = extract_chat_name_with_preview(row_img, include_preview=False)
    return n


def name_region_ocr_preview(row_img: Image.Image, *, max_chars: int = 400) -> str:
    _, p = extract_chat_name_with_preview(
        row_img, include_preview=True, max_preview_chars=max_chars
    )
    return p


# ── 7. 单次全扫描 ────────────────────────────────────────

def _is_valid_chat_name(name: str) -> bool:
    """粗筛无效的 OCR name（太短、纯数字、单字等）。"""
    if not name or len(name) < 2:
        return False
    if name.isdigit():
        return False
    return True


def scan_sidebar_once(window_img: Image.Image,
                      only_unread: bool = True,
                      require_name: bool = False,
                      window_bounds: Optional[Rect] = None) -> List[ChatInfo]:
    """对一张窗口截图做完整 sidebar 扫描。

    每个 row 独立 crop → 独立检测 badge/name，不跨 row。
    window_bounds 传入时写入 ChatInfo.window_rect。
    """
    sidebar_rect = detect_sidebar_region(window_img)
    sidebar_img = sidebar_rect.crop_from(window_img)
    rows = detect_session_rows(sidebar_img)

    results: List[ChatInfo] = []
    for row_rect in rows:
        row_img = row_rect.crop_from(sidebar_img)

        # ── row-local badge 检测 ──
        badge = detect_unread_badge(row_img)

        if only_unread and not badge["has_unread"]:
            continue

        # ── row-local name OCR ──
        name, ocr_raw = extract_chat_name_with_preview(row_img)
        if is_sidebar_ui_chrome_label(name):
            continue

        if require_name and not _is_valid_chat_name(name):
            continue

        conf = 0.85 if _is_valid_chat_name(name) else 0.3

        abs_row = Rect(
            sidebar_rect.x + row_rect.x,
            sidebar_rect.y + row_rect.y,
            row_rect.width,
            row_rect.height,
        )

        results.append(ChatInfo(
            name=name,
            unread_count=badge["unread_count"],
            badge_type=badge["badge_type"],
            confidence=conf,
            row_rect=abs_row,
            window_rect=window_bounds,
            name_ocr_raw=ocr_raw,
        ))
    return results


# ── 8. 辅助：sidebar 图像相似度 ─────────────────────────

def sidebar_images_similar(img1: Image.Image, img2: Image.Image,
                           threshold: float = 5.0) -> bool:
    """快速判断两张 sidebar 截图是否几乎相同（用于滚动停止检测）。"""
    a1 = np.array(img1.resize((100, 100))).astype(np.float32)
    a2 = np.array(img2.resize((100, 100))).astype(np.float32)
    return float(np.abs(a1 - a2).mean()) < threshold
