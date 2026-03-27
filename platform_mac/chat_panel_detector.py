"""右侧聊天面板检测：裁切、标题 OCR、ready 判断。

所有坐标均为 Retina 物理像素（截图原始分辨率）。
"""

from __future__ import annotations

import re

from PIL import Image

from platform_mac.ocr import ocr_image
from platform_mac.sidebar_detector import Rect, SIDEBAR_WIDTH_RATIO_FALLBACK, TITLEBAR_HEIGHT_RATIO, detect_sidebar_region


HEADER_HEIGHT_RATIO = 0.045

HEADER_LEFT_PAD = 20
HEADER_RIGHT_RATIO = 0.65

VIEWPORT_TOP_RATIO = 0.07
VIEWPORT_BOTTOM_RATIO = 0.10


def capture_right_panel(window_img: Image.Image) -> Image.Image:
    """从窗口截图中裁出右侧聊天区域（不含 sidebar）。"""
    w, h = window_img.size
    sidebar = detect_sidebar_region(window_img)
    left = sidebar.x2
    top = int(h * TITLEBAR_HEIGHT_RATIO)
    return window_img.crop((left, top, w, h))


def crop_chat_panel(window_img: Image.Image) -> Image.Image:
    """从窗口截图中裁出右侧完整面板（含标题栏和输入框）。

    等同于 capture_right_panel，语义更清晰。
    """
    return capture_right_panel(window_img)


def crop_chat_viewport(window_img: Image.Image) -> Image.Image:
    """从窗口截图中裁出纯消息气泡区域。

    去掉：左侧 sidebar、顶部标题栏/header、底部输入框/工具栏。
    只保留中间的消息可视区域。
    """
    w, h = window_img.size
    sidebar = detect_sidebar_region(window_img)
    left = sidebar.x2
    top = int(h * (TITLEBAR_HEIGHT_RATIO + VIEWPORT_TOP_RATIO))
    bottom = int(h * (1.0 - VIEWPORT_BOTTOM_RATIO))
    return window_img.crop((left, top, w, bottom))


def _crop_header(window_img: Image.Image) -> Image.Image:
    """从窗口截图中裁出右侧 header 标题栏。"""
    w, h = window_img.size
    sidebar = detect_sidebar_region(window_img)
    left = sidebar.x2 + HEADER_LEFT_PAD
    top = 4
    right = int(w * HEADER_RIGHT_RATIO)
    bottom = int(h * HEADER_HEIGHT_RATIO) + top
    bottom = max(bottom, top + 50)
    return window_img.crop((left, top, right, bottom))


def extract_chat_header_title(window_img: Image.Image) -> str:
    """从窗口截图右侧 header 区域 OCR 提取当前会话标题。"""
    header = _crop_header(window_img)
    results = ocr_image(header, min_confidence=0.3)
    if results:
        return results[0].text.strip()
    return ""


def get_header_image(window_img: Image.Image) -> Image.Image:
    """返回 header 裁切图（用于调试保存）。"""
    return _crop_header(window_img)


def _normalize_title(s: str) -> str:
    """标准化标题用于匹配：去除成员数、常见标点。"""
    s = s.strip()
    s = re.sub(r'[（(]\d+[）)]$', '', s)
    s = s.strip(" \t、，。：；""''")
    return s


def _extract_cjk_core(s: str) -> str:
    """提取字符串中的 CJK + 字母数字核心部分，去掉 emoji OCR 垃圾。"""
    # 保留 CJK、字母、数字
    return re.sub(r'[^\u4e00-\u9fffA-Za-z0-9]', '', s)


def titles_match(detected: str, target: str) -> bool:
    """模糊匹配：检测到的 header 标题是否与目标 chat name 对应。

    匹配策略（任一命中即为 True）：
      1. 标准化后完全相等
      2. 一方包含另一方（长度 >= 2）
      3. 标准化后前缀匹配（前 2+ 个字符相同）
      4. 字符级重叠率 >= 60%（容忍 OCR 噪声和 emoji 伪影）
    """
    if not detected or not target:
        return False

    dn = _normalize_title(detected)
    tn = _normalize_title(target)

    if not dn or not tn:
        return False

    # 1. 精确匹配
    if dn == tn:
        return True

    # 2. 包含匹配
    if len(tn) >= 2 and tn in dn:
        return True
    if len(dn) >= 2 and dn in tn:
        return True

    # 3. 前缀匹配
    prefix_len = min(3, len(dn), len(tn))
    if prefix_len >= 2 and dn[:prefix_len] == tn[:prefix_len]:
        return True

    # 4. 字符级重叠（处理 emoji OCR 伪影 + 单字 OCR 错误）
    dc = _extract_cjk_core(dn)
    tc = _extract_cjk_core(tn)
    if len(tc) >= 2 and len(dc) >= 2:
        short, long_ = (tc, dc) if len(tc) <= len(dc) else (dc, tc)
        common = sum(1 for c in short if c in long_)
        if common >= max(2, len(short) * 0.6):
            return True

    return False
