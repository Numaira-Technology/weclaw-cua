"""从滚动拼接后的聊天长图中提取消息（与 Step 3 的 long_image 对应）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from PIL import Image

from algo_a.extract_messages import DEFAULT_EXTRACT_MODEL
from algo_a.llm_image_prep import DEFAULT_MAX_SIDE_PIXELS
from algo_a.long_image_chunk_extract import (
    merge_chunk_messages,
    split_vertical_strips,
    vertical_chunk_count_for_height,
)
from algo_a.read_visible_messages import Message, _build_prompt, _extract_once


def _build_prompt_long(chat_name: str) -> str:
    p = _build_prompt(chat_name)
    p = p.replace(
        "You are reading a WeChat group chat screenshot.",
        "You are reading a vertically stitched WeChat chat screenshot (scroll-capture long image).",
        1,
    ).replace(
        "Extract ALL visible messages from this screenshot",
        "Extract ALL visible messages from this full-length image (entire vertical extent)",
        1,
    )
    return (
        p
        + "\n13. Stitched long images may show the same bubble twice at scroll seams; "
        "if two entries have the same sender and the same visible text, output only one.\n"
    )


def _build_prompt_long_chunk(chat_name: str, part_index: int, part_total: int) -> str:
    base = _build_prompt_long(chat_name)
    suffix = (
        f"\n\nThis image is vertical segment {part_index} of {part_total} of the same "
        "scroll-captured long chat. Extract ONLY messages visible in this segment, "
        "top-to-bottom."
    )
    return base + suffix


def extract_long_image_messages(
    long_img: Image.Image,
    chat_name: str,
    model: str = DEFAULT_EXTRACT_MODEL,
    max_retries: int = 3,
    llm_timeout: float = 300.0,
    max_side_pixels: int = DEFAULT_MAX_SIDE_PIXELS,
    chunk_count: int = 2,
    chunk_overlap_ratio: float = 0.08,
    chunk_max_strip_height_px: int = 2400,
    chunk_max_count: int = 10,
) -> Tuple[List[Message], Dict[str, Any]]:
    _, h = long_img.size
    if chunk_max_strip_height_px > 0:
        effective_chunks = vertical_chunk_count_for_height(
            h, chunk_max_strip_height_px, chunk_max_count,
        )
    else:
        effective_chunks = chunk_count
    assert effective_chunks >= 1

    if effective_chunks == 1:
        prompt = _build_prompt_long(chat_name)
        last_error: Exception | None = None
        for attempt in range(max_retries):
            try:
                msgs, meta = _extract_once(
                    long_img,
                    chat_name,
                    model,
                    prompt=prompt,
                    timeout=llm_timeout,
                    max_side_pixels=max_side_pixels,
                )
                meta["chunked"] = False
                meta["chunk_count"] = 1
                meta["effective_chunk_count"] = 1
                meta["chunk_max_strip_height_px"] = chunk_max_strip_height_px
                meta["chunk_max_count"] = chunk_max_count
                meta["long_image_height_px"] = h
                return msgs, meta
            except Exception as exc:
                last_error = exc
                print(f"[read_long_image] attempt {attempt + 1}/{max_retries} failed: {exc}")
                if attempt < max_retries - 1:
                    continue
                raise
        assert last_error is not None
        raise last_error

    strips = split_vertical_strips(long_img, effective_chunks, chunk_overlap_ratio)
    parts: List[List[Message]] = []
    chunks_meta: List[Dict[str, Any]] = []
    last_error: Exception | None = None
    for i, strip in enumerate(strips):
        prompt = _build_prompt_long_chunk(chat_name, i + 1, effective_chunks)
        chunk_ok = False
        for attempt in range(max_retries):
            try:
                msgs, meta = _extract_once(
                    strip,
                    chat_name,
                    model,
                    prompt=prompt,
                    timeout=llm_timeout,
                    max_side_pixels=max_side_pixels,
                )
                meta["chunk_index"] = i + 1
                meta["chunk_total"] = effective_chunks
                chunks_meta.append(meta)
                parts.append(msgs)
                chunk_ok = True
                break
            except Exception as exc:
                last_error = exc
                print(
                    f"[read_long_image] chunk {i + 1}/{effective_chunks} "
                    f"attempt {attempt + 1}/{max_retries} failed: {exc}",
                )
                if attempt < max_retries - 1:
                    continue
        if not chunk_ok:
            assert last_error is not None
            raise last_error

    merged = merge_chunk_messages(parts)
    combined: Dict[str, Any] = {
        "chunked": True,
        "chunk_count": effective_chunks,
        "effective_chunk_count": effective_chunks,
        "chunk_max_strip_height_px": chunk_max_strip_height_px,
        "chunk_max_count": chunk_max_count,
        "chunk_overlap_ratio": chunk_overlap_ratio,
        "long_image_height_px": h,
        "chunks": chunks_meta,
        "model": model,
        "message_count": len(merged),
        "max_side_pixels": max_side_pixels,
        "chunk_raw_texts": [c.get("raw_text", "") for c in chunks_meta],
    }
    return merged, combined


def read_messages_from_long_image_file(
    path: str | Path,
    chat_name: str,
    model: str = DEFAULT_EXTRACT_MODEL,
    llm_timeout: float = 300.0,
    max_side_pixels: int = DEFAULT_MAX_SIDE_PIXELS,
    chunk_count: int = 2,
    chunk_overlap_ratio: float = 0.08,
    chunk_max_strip_height_px: int = 2400,
    chunk_max_count: int = 10,
) -> Tuple[List[Message], Image.Image, Dict[str, Any]]:
    p = Path(path)
    assert p.is_file(), f"long image not found: {p}"
    long_img = Image.open(p).convert("RGB")
    messages, meta = extract_long_image_messages(
        long_img,
        chat_name,
        model=model,
        llm_timeout=llm_timeout,
        max_side_pixels=max_side_pixels,
        chunk_count=chunk_count,
        chunk_overlap_ratio=chunk_overlap_ratio,
        chunk_max_strip_height_px=chunk_max_strip_height_px,
        chunk_max_count=chunk_max_count,
    )
    meta["long_image_path"] = str(p.resolve())
    meta["long_image_size"] = long_img.size
    return messages, long_img, meta
