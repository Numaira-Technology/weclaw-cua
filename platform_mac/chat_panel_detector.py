"""右侧聊天面板检测：裁切、标题 OCR、ready 判断。

所有坐标均为 Retina 物理像素（截图原始分辨率）。
"""

from __future__ import annotations

import math
import re

from typing import List, Optional

from PIL import Image

from platform_mac.ocr import ocr_image, prepare_image_for_vision_ocr
from platform_mac.sidebar_detector import TITLEBAR_HEIGHT_RATIO, detect_sidebar_region


HEADER_BAND_MIN_PX = 40
HEADER_BAND_MAX_PX = 96
HEADER_BAND_HEIGHT_RATIO = 0.036

HEADER_LEFT_PAD = 20
HEADER_PANEL_WIDTH_RATIO = 0.82

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


def _header_band_height_px(h: int) -> int:
    band = int(h * HEADER_BAND_HEIGHT_RATIO)
    return max(HEADER_BAND_MIN_PX, min(HEADER_BAND_MAX_PX, band))


def _header_band_rects(window_img: Image.Image) -> List[tuple[int, int, int, int]]:
    """右侧面板内多条水平标题带（不同垂直偏移），应对微信顶栏高度与版本差异。"""
    w, h = window_img.size
    sidebar = detect_sidebar_region(window_img)
    left = sidebar.x2 + HEADER_LEFT_PAD
    panel_inner = w - sidebar.x2 - HEADER_LEFT_PAD - 8
    right = min(w - 8, sidebar.x2 + HEADER_LEFT_PAD + int(panel_inner * HEADER_PANEL_WIDTH_RATIO))
    band = _header_band_height_px(h)
    tb = int(h * TITLEBAR_HEIGHT_RATIO)
    tops = (
        tb + 2,
        tb + 2 + int(h * 0.020),
        tb + 2 + int(h * 0.038),
        int(h * 0.036) + 2,
        int(h * 0.048) + 2,
    )
    seen: set[tuple[int, int, int, int]] = set()
    out: List[tuple[int, int, int, int]] = []
    for top in tops:
        top = max(2, min(top, h - band - 6))
        bottom = min(h - 4, top + band)
        if right <= left or bottom <= top:
            continue
        key = (left, top, right, bottom)
        if key not in seen:
            seen.add(key)
            out.append(key)
    assert out
    return out


def _crop_header(window_img: Image.Image) -> Image.Image:
    """单条主标题带（与 _header_band_rects 第一条一致），供调试图与旧行为对齐。"""
    left, top, right, bottom = _header_band_rects(window_img)[0]
    return window_img.crop((left, top, right, bottom))


def _name_like_letter_count(s: str) -> int:
    return sum(
        1
        for c in s
        if "\u4e00" <= c <= "\u9fff" or ("A" <= c <= "Z") or ("a" <= c <= "z")
    )


def _digit_count(s: str) -> int:
    return sum(1 for c in s if c.isdigit())


def _is_reaction_or_junk_title(s: str) -> bool:
    s = s.strip()
    if len(s) <= 1:
        return True
    junk = sum(
        1
        for c in s
        if c in "+0123456789⑦⑧⑨⑩①②③④⑤⑥⑪⑫⑬⑭⑮ \t·.。:："
    )
    if junk >= len(s) * 0.5:
        return True
    if "+" in s and re.match(r"^[\+\d\s⑦⑧⑨⑩①②③④⑤⑥]+$", s):
        return True
    if re.match(r"^[（(]\d{1,3}[）)]", s):
        if _digit_count(s) >= 3 and _name_like_letter_count(s) <= 3:
            return True
    return False


def _header_ocr_lines_by_band(window_img: Image.Image) -> List[List[str]]:
    bands: List[List[str]] = []
    for left, top, right, bottom in _header_band_rects(window_img):
        band_img = window_img.crop((left, top, right, bottom))
        prepared = prepare_image_for_vision_ocr(band_img, min_side=48)
        results = ocr_image(prepared, min_confidence=0.0)
        ordered = sorted(results, key=lambda r: (r.pixel_y, r.x))
        seen_band: set[str] = set()
        line_list: List[str] = []
        for r in ordered:
            t = r.text.strip()
            if t and t not in seen_band:
                seen_band.add(t)
                line_list.append(t)
        bands.append(line_list)
    return bands


def _dedup_flatten_header_bands(bands: List[List[str]]) -> List[str]:
    seen_text: set[str] = set()
    out: List[str] = []
    for line_list in bands:
        for t in line_list:
            if t not in seen_text:
                seen_text.add(t)
                out.append(t)
    return out


def _ordered_header_ocr_lines(window_img: Image.Image) -> List[str]:
    return _dedup_flatten_header_bands(_header_ocr_lines_by_band(window_img))


def list_header_ocr_lines(window_img: Image.Image) -> List[str]:
    """调试：多 band 合并后的 OCR 行（去重保序）。"""
    return _ordered_header_ocr_lines(window_img)


_HEADER_FALLBACK_BANDS = 2


def extract_chat_header_title(
    window_img: Image.Image,
    match_hint: Optional[str] = None,
) -> str:
    """从右侧标题带 OCR；多行时优先与 match_hint 匹配，并跳过反应数等碎片。

    无 hint 命中时只在最靠前若干条 header 带里取非 junk 行，避免把消息区 OCR
    （如经文/摘要误识为 （7）7-1Sa1）当作标题，导致已进入会话却校验失败。
    """
    bands = _header_ocr_lines_by_band(window_img)
    lines = _dedup_flatten_header_bands(bands)
    if not lines:
        return ""
    hint = match_hint.strip() if match_hint else ""
    if hint:
        for t in lines:
            if titles_match(t, hint):
                return t
    limit = min(_HEADER_FALLBACK_BANDS, len(bands))
    for bi in range(limit):
        for t in bands[bi]:
            if not _is_reaction_or_junk_title(t):
                return t
    return ""


def get_header_image(window_img: Image.Image) -> Image.Image:
    """返回 header 裁切图（用于调试保存）。"""
    return _crop_header(window_img)


def _normalize_title(s: str) -> str:
    """标准化标题用于匹配：去除成员数、常见标点；合并空格与连字符类分隔（test 2 ≈ test-2）。"""
    s = s.strip()
    s = re.sub(r'[（(]\d+[）)]$', '', s)
    s = s.strip(" \t、，。：；""''")
    s = re.sub(r"[\s\-_–—·]+", "", s)
    return s


def _extract_cjk_core(s: str) -> str:
    """提取字符串中的 CJK + 字母数字核心部分，去掉 emoji OCR 垃圾。"""
    # 保留 CJK、字母、数字
    return re.sub(r'[^\u4e00-\u9fffA-Za-z0-9]', '', s)


def _hyphenated_last_segment_clash(a: str, b: str) -> bool:
    """同一 stem、最后一节不同（如 test-1 vs test-2），不得判为同一会话。"""
    if "-" not in a or "-" not in b:
        return False
    a1, a2 = a.rsplit("-", 1)
    b1, b2 = b.rsplit("-", 1)
    if a1.casefold() != b1.casefold():
        return False
    return a2 != b2


def _ascii_core_numeric_suffix_clash(a: str, b: str) -> bool:
    """_extract_cjk_core 后 test1 vs test2：同字母 stem、不同数字尾，不得靠重叠判同一。"""
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*\d+", a) or not re.fullmatch(
        r"[A-Za-z][A-Za-z0-9]*\d+", b
    ):
        return False
    ma = re.match(r"^(.+?)(\d+)$", a)
    mb = re.match(r"^(.+?)(\d+)$", b)
    assert ma and mb
    if ma.group(1).casefold() != mb.group(1).casefold():
        return False
    return ma.group(2) != mb.group(2)


def strict_chat_name_match(detected: str, target: str) -> bool:
    """侧栏名与 config 群名是否一致（strip + ASCII 大小写不敏感），用于批处理精确选行。"""
    if not detected or not target:
        return False
    a = detected.strip()
    b = target.strip()
    return a == b or a.casefold() == b.casefold()


def titles_match(detected: str, target: str) -> bool:
    """模糊匹配：检测到的 header / 侧栏名是否与目标 chat name 对应。

    匹配策略（任一命中即为 True）：
      1. 标准化后完全相等（ASCII 大小写不敏感）
      2. 一方包含另一方（长度 >= 2）
      3. 整段前缀（一方为另一方完整前缀；避免仅用前 3 字导致 test-1 / test-2 误判）
      4. 字符级重叠：须达到 ceil(0.72*短串长) 且至少 3（避免 bitter vs test-2 仅靠 t/e 误判）
    """
    if not detected or not target:
        return False

    dn = _normalize_title(detected)
    tn = _normalize_title(target)

    if not dn or not tn:
        return False

    # 1. 精确匹配（ASCII 标题大小写不敏感）
    if dn == tn or dn.casefold() == tn.casefold():
        return True

    # 2. 包含匹配
    if len(tn) >= 2 and tn in dn:
        return True
    if len(dn) >= 2 and dn in tn:
        return True
    if len(tn) >= 2 and tn.casefold() in dn.casefold():
        return True
    if len(dn) >= 2 and dn.casefold() in tn.casefold():
        return True

    if _hyphenated_last_segment_clash(dn, tn):
        return False

    # 3. 整段前缀
    if len(tn) >= 2 and (dn.startswith(tn) or tn.startswith(dn)):
        return True
    dnf, tnf = dn.casefold(), tn.casefold()
    if len(tn) >= 2 and (dnf.startswith(tnf) or tnf.startswith(dnf)):
        return True

    # 4. 字符级重叠（处理 emoji OCR 伪影 + 单字 OCR 错误）
    dc = _extract_cjk_core(dn)
    tc = _extract_cjk_core(tn)
    if len(tc) >= 2 and len(dc) >= 2:
        short, long_ = (tc, dc) if len(tc) <= len(dc) else (dc, tc)
        common = sum(1 for c in short if c in long_)
        need = max(3, math.ceil(len(short) * 0.72))
        if common >= need:
            if _hyphenated_last_segment_clash(dc, tc):
                return False
            if _ascii_core_numeric_suffix_clash(dc, tc):
                return False
            return True

    return False
