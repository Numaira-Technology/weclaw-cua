"""长图竖向切条、分段送 vision LLM、合并消息。"""

from __future__ import annotations

from typing import List

from PIL import Image

from algo_a.read_visible_messages import Message


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
    if n == 2:
        mid = h // 2
        y1_end = min(h, mid + overlap // 2)
        y2_start = max(0, mid - overlap // 2)
        return [
            img.crop((0, 0, w, y1_end)),
            img.crop((0, y2_start, w, h)),
        ]
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


def merge_chunk_messages(parts: List[List[Message]]) -> List[Message]:
    """按条带顺序拼接，相邻重复（重叠区）去重；仅比较 sender、content、type。"""
    merged: List[Message] = []
    for part in parts:
        for m in part:
            if merged:
                p = merged[-1]
                if (
                    p.sender == m.sender
                    and p.content == m.content
                    and p.type == m.type
                ):
                    continue
            merged.append(m)
    return merged
