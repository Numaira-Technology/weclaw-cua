"""长图竖向切条、分段送 vision LLM、合并消息。"""

from __future__ import annotations

from typing import List

from PIL import Image

from algo_a.read_visible_messages import Message


def vertical_chunk_count_for_height(
    height_px: int,
    max_strip_height_px: int,
    max_chunks: int,
) -> int:
    """按单条最大高度估算竖向条数，不超过 max_chunks。"""
    assert height_px > 0
    assert max_chunks >= 1
    if max_strip_height_px <= 0:
        return 1
    if height_px <= max_strip_height_px:
        return 1
    n = (height_px + max_strip_height_px - 1) // max_strip_height_px
    return min(max(n, 1), max_chunks)


def split_vertical_strips(
    img: Image.Image,
    n: int,
    overlap_ratio: float = 0.08,
) -> List[Image.Image]:
    """将长图沿竖直方向切成 n 条，相邻条带重叠以减少截断气泡。"""
    assert n >= 1
    w, h = img.size
    if n == 1:
        return [img]
    overlap = max(30, int(h * overlap_ratio))
    boundaries = [int(i * h / n) for i in range(n + 1)]
    out: List[Image.Image] = []
    for i in range(n):
        y0 = 0 if i == 0 else boundaries[i] - overlap // 2
        y1 = h if i == n - 1 else boundaries[i + 1] + overlap // 2
        y0 = max(0, y0)
        y1 = min(h, y1)
        assert y1 > y0
        out.append(img.crop((0, y0, w, y1)))
    return out


def merge_chunk_messages(parts: List[List[Message]], lookback: int = 5) -> List[Message]:
    """按条带顺序拼接；在滑动窗口内按 sender+content+type 去重（接缝与重叠区）。"""
    merged: List[Message] = []
    for part in parts:
        for m in part:
            dup = False
            for prev in merged[-lookback:]:
                if (
                    prev.sender == m.sender
                    and prev.content == m.content
                    and prev.type == m.type
                ):
                    dup = True
                    break
            if not dup:
                merged.append(m)
    return merged
