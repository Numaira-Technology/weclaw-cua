"""单群闭环：点击 → 滚动长图 → LLM（extract_messages 或 read_long_image）→ 后处理 → JSON。"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

from platform_mac.sidebar_detector import ChatInfo
from algo_a.click_into_chat import click_into_chat, ClickResult
from algo_a.capture_chat import CaptureSettings, capture_and_stitch
from algo_a.extract_messages import DEFAULT_EXTRACT_MODEL
from algo_a.llm_image_prep import DEFAULT_MAX_SIDE_PIXELS
from algo_a.postprocess_messages import postprocess
from algo_a.process_one_chat_llm import (
    run_extract_messages_backend,
    run_read_long_image_backend,
)
from algo_a.write_messages_json import write_messages_json

ExtractBackend = Literal["extract_messages", "read_long_image"]


@dataclass
class ProcessResult:
    """单群处理的完整结果。"""
    chat_name: str
    success: bool
    message_count: int = 0
    json_path: str = ""
    long_image_path: str = ""
    click_result: Optional[ClickResult] = None
    frame_count: int = 0
    extraction_confidence: str = ""
    raw_message_count: int = 0
    error: str = ""
    timings: Dict[str, float] = field(default_factory=dict)
    extract_backend: str = "extract_messages"


def process_one_chat(
    driver,
    chat_info: ChatInfo,
    output_dir: str = "output",
    capture_settings: Optional[CaptureSettings] = None,
    model: str = DEFAULT_EXTRACT_MODEL,
    skip_click: bool = False,
    save_frames: bool = False,
    vision_max_side_pixels: int = DEFAULT_MAX_SIDE_PIXELS,
    click_timeout: float = 5.0,
    click_max_retries: int = 1,
    extract_backend: ExtractBackend = "extract_messages",
    extract_llm_timeout: float = 300.0,
    read_long_chunk_count: int = 2,
    read_long_chunk_overlap: float = 0.08,
    read_long_chunk_max_strip_height_px: int = 2400,
    read_long_chunk_max_count: int = 10,
) -> ProcessResult:
    """extract_backend: extract_messages | read_long_image；后者用 read_long_chunk_*。"""
    chat_name = chat_info.name or "unnamed"
    safe_name = chat_name.replace("/", "_").replace("\\", "_").replace(":", "_")
    chat_dir = os.path.join(output_dir, safe_name)
    os.makedirs(chat_dir, exist_ok=True)

    result = ProcessResult(chat_name=chat_name, success=False, extract_backend=extract_backend)
    t_total = time.time()

    t0 = time.time()
    if not skip_click:
        click_res = click_into_chat(
            driver, chat_info, timeout=click_timeout, max_retries=click_max_retries,
        )
        result.click_result = click_res
        if not click_res.ready:
            result.error = f"进入会话失败: {click_res.reason} — {click_res.error}"
            result.timings["click"] = time.time() - t0
            print(f"[process] ✗ {chat_name}: {result.error}")
            return result
        print(f"[process] ✓ 进入会话: {click_res.detected_title}")
    else:
        print(f"[process] 跳过点击，假设已在: {chat_name}")
    result.timings["click"] = time.time() - t0

    llm_chat_name = chat_name
    if not skip_click and result.click_result and result.click_result.detected_title:
        llm_chat_name = result.click_result.detected_title

    time.sleep(0.3)

    t0 = time.time()
    frame_dir = os.path.join(chat_dir, "frames") if save_frames else None
    long_image_path = os.path.join(chat_dir, "long_image.png")

    print(
        "[process] 滚动截图 + 拼接长图（每帧约 5–15s，默认最多 15 帧）…",
        flush=True,
        file=sys.stderr,
    )

    try:
        stitch_result = capture_and_stitch(
            driver=driver,
            output_path=long_image_path,
            capture_dir=frame_dir,
            chat_name=safe_name,
            settings=capture_settings,
        )
    except Exception as e:
        result.error = f"截图/拼接失败: {e}"
        result.timings["capture"] = time.time() - t0
        print(f"[process] ✗ {chat_name}: {result.error}")
        return result

    long_image = stitch_result["long_image"]
    result.frame_count = stitch_result["pass_count"]
    result.long_image_path = os.path.abspath(long_image_path)
    result.timings["capture"] = time.time() - t0
    print(f"[process] 拼接完成: {result.frame_count} 帧, {long_image.size[0]}x{long_image.size[1]}px")

    t0 = time.time()
    print(
        f"[process] LLM 解析长图 backend={extract_backend!r}（大图可能需数分钟）…",
        flush=True,
        file=sys.stderr,
    )
    try:
        if extract_backend == "extract_messages":
            raw_messages, side_meta = run_extract_messages_backend(
                long_image, model, vision_max_side_pixels,
            )
        else:
            raw_messages, side_meta = run_read_long_image_backend(
                long_image,
                llm_chat_name,
                model,
                vision_max_side_pixels,
                extract_llm_timeout,
                read_long_chunk_count,
                read_long_chunk_overlap,
                read_long_chunk_max_strip_height_px,
                read_long_chunk_max_count,
            )
    except Exception as e:
        try:
            long_image.save(long_image_path, format="PNG")
        except Exception:
            pass
        result.long_image_path = os.path.abspath(long_image_path)
        result.error = f"LLM 提取失败: {e}"
        result.timings["extract"] = time.time() - t0
        print(f"[process] ✗ {chat_name}: {result.error}")
        return result

    result.raw_message_count = len(raw_messages)
    result.extraction_confidence = str(side_meta.get("extraction_confidence", "unknown"))
    result.timings["extract"] = time.time() - t0
    print(
        f"[process] LLM 提取: {len(raw_messages)} 条 (confidence={result.extraction_confidence})",
    )

    t0 = time.time()
    processed = postprocess(raw_messages, chat_name)
    result.timings["postprocess"] = time.time() - t0
    dedup_removed = result.raw_message_count - len(processed)
    if dedup_removed > 0:
        print(f"[process] 后处理: {result.raw_message_count} → {len(processed)} 条 (去重 {dedup_removed})")

    t0 = time.time()
    extra_meta = {
        "frame_count": result.frame_count,
        "extraction_confidence": result.extraction_confidence,
        "raw_message_count": result.raw_message_count,
        "model": model,
        "long_image": os.path.basename(long_image_path),
        "extract_backend": extract_backend,
    }
    if extract_backend == "read_long_image" and "read_long_image_meta" in side_meta:
        extra_meta["read_long_image_meta"] = side_meta["read_long_image_meta"]
    if extract_backend == "extract_messages" and side_meta.get("boundary_stability"):
        extra_meta["boundary_stability"] = side_meta["boundary_stability"]

    json_path = write_messages_json(
        chat_name=chat_name,
        messages=processed,
        output_dir=chat_dir,
        extra_meta=extra_meta,
    )
    result.json_path = json_path
    result.message_count = len(processed)
    result.timings["write"] = time.time() - t0

    result.success = True
    result.timings["total"] = time.time() - t_total
    print(
        f"[process] ✓ {chat_name}: {result.message_count} 条消息 → {json_path}"
        f"  ({result.timings['total']:.1f}s)"
    )
    return result
