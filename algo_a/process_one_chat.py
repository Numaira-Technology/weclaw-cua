"""单群闭环：点击进入 → 滚动截图 → 长图拼接 → LLM 提取 → 后处理 → 写 JSON。

这是最小完整流程，不含多群循环、不含新消息类型扩展。

用法：
    from algo_a.process_one_chat import process_one_chat
    result = process_one_chat(driver, chat_info, output_dir="output")
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from PIL import Image

from platform_mac.sidebar_detector import ChatInfo
from algo_a.click_into_chat import click_into_chat, ClickResult
from algo_a.capture_chat import CaptureSettings, capture_and_stitch
from algo_a.extract_messages import DEFAULT_EXTRACT_MODEL, extract_messages
from algo_a.llm_image_prep import DEFAULT_MAX_SIDE_PIXELS
from algo_a.postprocess_messages import postprocess
from algo_a.write_messages_json import write_messages_json


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
) -> ProcessResult:
    """处理单个群聊的完整流程。

    参数：
      driver           — 已初始化的 MacDriver
      chat_info        — 目标会话（含 name, row_rect, window_rect）
      output_dir       — 输出根目录，会在下面建 {chat_name}/ 子目录
      capture_settings — 滚动截图配置（None 用默认）
      model            — vision LLM 模型标识
      skip_click       — 跳过点击步骤（已在目标会话中时使用）
      save_frames      — 是否保存每帧截图
      vision_max_side_pixels — 送 LLM 前长图长边像素上限（减轻编码与 API 负担）
      click_timeout       — 等待右侧面板标题匹配的最长时间（秒）
      click_max_retries   — 点击失败后 rescan 重试次数（见 click_into_chat）

    返回 ProcessResult。
    """
    chat_name = chat_info.name or "unnamed"
    safe_name = chat_name.replace("/", "_").replace("\\", "_").replace(":", "_")
    chat_dir = os.path.join(output_dir, safe_name)
    os.makedirs(chat_dir, exist_ok=True)

    result = ProcessResult(chat_name=chat_name, success=False)
    t_total = time.time()

    # ── Step 1: 点击进入 ─────────────────────────────────
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

    time.sleep(0.3)

    # ── Step 2: 滚动截图 + 拼接长图 ──────────────────────
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

    long_image: Image.Image = stitch_result["long_image"]
    result.frame_count = stitch_result["pass_count"]
    result.long_image_path = os.path.abspath(long_image_path)
    result.timings["capture"] = time.time() - t0
    print(f"[process] 拼接完成: {result.frame_count} 帧, {long_image.size[0]}x{long_image.size[1]}px")

    # ── Step 3: LLM 提取消息 ─────────────────────────────
    t0 = time.time()
    print(
        "[process] 调用 LLM 解析长图（大图可能需数分钟，请耐心等待）…",
        flush=True,
        file=sys.stderr,
    )
    try:
        extract_result = extract_messages(
            long_image,
            model=model,
            max_side_pixels=vision_max_side_pixels,
        )
    except Exception as e:
        result.error = f"LLM 提取失败: {e}"
        result.timings["extract"] = time.time() - t0
        print(f"[process] ✗ {chat_name}: {result.error}")
        return result

    raw_messages = extract_result.get("messages", [])
    result.raw_message_count = len(raw_messages)
    result.extraction_confidence = extract_result.get("extraction_confidence", "unknown")
    result.timings["extract"] = time.time() - t0
    print(f"[process] LLM 提取: {len(raw_messages)} 条 (confidence={result.extraction_confidence})")

    # ── Step 4: 后处理 ───────────────────────────────────
    t0 = time.time()
    processed = postprocess(raw_messages, chat_name)
    result.timings["postprocess"] = time.time() - t0
    dedup_removed = result.raw_message_count - len(processed)
    if dedup_removed > 0:
        print(f"[process] 后处理: {result.raw_message_count} → {len(processed)} 条 (去重 {dedup_removed})")

    # ── Step 5: 写 JSON ──────────────────────────────────
    t0 = time.time()
    extra_meta = {
        "frame_count": result.frame_count,
        "extraction_confidence": result.extraction_confidence,
        "raw_message_count": result.raw_message_count,
        "model": model,
        "long_image": os.path.basename(long_image_path),
    }
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
