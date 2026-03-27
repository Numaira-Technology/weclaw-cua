"""process_one_chat 的 LLM 抽取：whole_pic extract_messages 与 read_long_image_messages。"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from PIL import Image

from algo_a.extract_messages import extract_messages
from algo_a.read_long_image_messages import extract_long_image_messages


def run_extract_messages_backend(
    long_image: Image.Image,
    model: str,
    max_side_pixels: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    r = extract_messages(long_image, model=model, max_side_pixels=max_side_pixels)
    raw = r.get("messages", [])
    side_meta = {
        "extraction_confidence": r.get("extraction_confidence", "unknown"),
        "boundary_stability": r.get("boundary_stability", ""),
    }
    return raw, side_meta


def run_read_long_image_backend(
    long_image: Image.Image,
    chat_name: str,
    model: str,
    max_side_pixels: int,
    llm_timeout: float,
    chunk_count: int,
    chunk_overlap_ratio: float,
    chunk_max_strip_height_px: int,
    chunk_max_count: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    msgs, meta = extract_long_image_messages(
        long_image,
        chat_name,
        model=model,
        llm_timeout=llm_timeout,
        max_side_pixels=max_side_pixels,
        chunk_count=chunk_count,
        chunk_overlap_ratio=chunk_overlap_ratio,
        chunk_max_strip_height_px=chunk_max_strip_height_px,
        chunk_max_count=chunk_max_count,
    )
    raw: List[Dict[str, Any]] = []
    for m in msgs:
        raw.append({
            "sender": m.sender,
            "time": m.time,
            "content": m.content,
            "type": m.type,
        })
    side_meta = {
        "extraction_confidence": "unknown",
        "read_long_image_meta": meta,
    }
    return raw, side_meta
