"""从滚动拼接后的聊天长图中提取消息（与 Step 3 的 long_image 对应）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from PIL import Image

from algo_a.llm_image_prep import DEFAULT_MAX_SIDE_PIXELS
from algo_a.long_image_chunk_extract import merge_chunk_messages, split_vertical_strips
from algo_a.read_visible_messages import Message, _build_prompt, _extract_once


def _build_prompt_long(chat_name: str) -> str:
    p = _build_prompt(chat_name)
    return p.replace(
        "You are reading a WeChat group chat screenshot.",
        "You are reading a vertically stitched WeChat chat screenshot (scroll-capture long image).",
        1,
    ).replace(
        "Extract ALL visible messages from this screenshot",
        "Extract ALL visible messages from this full-length image (entire vertical extent)",
        1,
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
    model: str = "openrouter/google/gemini-2.5-flash",
    max_retries: int = 3,
    llm_timeout: float = 300.0,
    max_side_pixels: int = DEFAULT_MAX_SIDE_PIXELS,
    chunk_count: int = 1,
    chunk_overlap_ratio: float = 0.08,
) -> Tuple[List[Message], Dict[str, Any]]:
    assert chunk_count >= 1
    if chunk_count == 1:
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
                return msgs, meta
            except Exception as exc:
                last_error = exc
                print(f"[read_long_image] attempt {attempt + 1}/{max_retries} failed: {exc}")
                if attempt < max_retries - 1:
                    continue
                raise
        assert last_error is not None
        raise last_error

    strips = split_vertical_strips(long_img, chunk_count, chunk_overlap_ratio)
    parts: List[List[Message]] = []
    chunks_meta: List[Dict[str, Any]] = []
    last_error: Exception | None = None
    for i, strip in enumerate(strips):
        prompt = _build_prompt_long_chunk(chat_name, i + 1, chunk_count)
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
                meta["chunk_total"] = chunk_count
                chunks_meta.append(meta)
                parts.append(msgs)
                chunk_ok = True
                break
            except Exception as exc:
                last_error = exc
                print(
                    f"[read_long_image] chunk {i + 1}/{chunk_count} "
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
        "chunk_count": chunk_count,
        "chunk_overlap_ratio": chunk_overlap_ratio,
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
    model: str = "openrouter/google/gemini-2.5-flash",
    llm_timeout: float = 300.0,
    max_side_pixels: int = DEFAULT_MAX_SIDE_PIXELS,
    chunk_count: int = 1,
    chunk_overlap_ratio: float = 0.08,
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
    )
    meta["long_image_path"] = str(p.resolve())
    meta["long_image_size"] = long_img.size
    return messages, long_img, meta
