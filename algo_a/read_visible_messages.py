"""读取聊天消息（vision LLM）。

- 单帧：截图 → 裁切 viewport → 提取（见 extract_viewport_messages / read_visible_messages）。
- 长图：用 read_long_image_messages 模块从 Step 3 拼接长图提取。

支持的消息类型：text, system, link_card, image, video, voice, call, unsupported, other（与 TESTING.md §3.3 一致）
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from PIL import Image

from algo_a.extract_messages import DEFAULT_EXTRACT_MODEL
from algo_a.llm_image_prep import DEFAULT_MAX_SIDE_PIXELS, downscale_max_side
from algo_a.llm_image_prep import pil_to_vision_payload
from algo_a.llm_openrouter_headers import ensure_openrouter_ascii_env, openrouter_completion_headers
from shared.openrouter_api_key import resolve_openrouter_api_key
from shared.openrouter_litellm_model import litellm_openrouter_model
from shared.vision_image_codec import log_vision_timing
from platform_mac.chat_panel_detector import crop_chat_viewport


@dataclass
class Message:
    """单条聊天消息。"""
    chat_name: str
    sender: str
    time: Optional[str]
    content: str
    type: str  # text | system | link_card | image | video | voice | call | unsupported | other


def _sanitize_chat_name_for_prompt(chat_name: str) -> str:
    s = chat_name.replace("\u201c", '"').replace("\u201d", '"')
    s = s.replace("\u2018", "'").replace("\u2019", "'").replace("\uff02", '"')
    return s


def _build_prompt(chat_name: str) -> str:
    label = _sanitize_chat_name_for_prompt(chat_name)
    return (
        f"You are reading a WeChat group chat screenshot. "
        f"The chat name is: \"{label}\"\n\n"
        "Extract ALL visible messages from this screenshot and return JSON only.\n\n"
        "Rules:\n"
        "1. Follow the JSON schema exactly.\n"
        "2. Keep messages in top-to-bottom visual order.\n"
        "3. For each message, extract: sender, time, content, type.\n"
        '4. If time is not explicitly shown above or near a message, use null.\n'
        '5. If sender is unclear, use "UNKNOWN".\n'
        '6. Do NOT output standalone date/time separator rows (gray bar showing only '
        'a date or "HH:MM") as messages—omit them. For real system notices '
        '(join/leave/recall), use sender="SYSTEM", type="system".\n'
        '7. For link/share/mini-program cards, extract visible title into content, '
        'type="link_card".\n'
        '8. For image messages where no text is visible, set content="[图片]", type="image". '
        'For video bubbles use type="video" and content="[视频]" (add visible caption after a space if any). '
        'For voice bubbles use type="voice" and one content line: "[语音]" plus visible duration '
        '(seconds or mm:ss); never add a separate message that is only the duration. '
        'For file bubbles use type="unsupported" and content like "[文件] name". '
        'For voice/video call status rows (Canceled, Missed, 未接听, 通话时长), '
        'use type="call" and put the visible status in content.\n'
        "8r. For reply/quote bubbles (引用 + reply), use one message: type=\"text\", "
        "content with the quoted part and the reply separated clearly (e.g. two paragraphs).\n"
        "9. Do NOT invent content that is not visible.\n"
        "10. Do NOT include the chat title bar or input box text as messages.\n"
        "11. Time-only lines are not messages; never emit an entry whose content is "
        "only a timestamp or date string.\n"
        "12. If the same sender posts nearly identical duplicate text (e.g. repeated "
        "ads), output a single message.\n\n"
        "JSON schema:\n"
        "{\n"
        '  "messages": [\n'
        "    {\n"
        '      "sender": "string",\n'
        '      "time": "string|null",\n'
        '      "content": "string",\n'
        '      "type": "text|system|link_card|image|video|voice|call|unsupported|other"\n'
        "    }\n"
        "  ],\n"
        '  "extraction_confidence": "high|medium|low"\n'
        "}"
    )


def _strip_code_fence(text: str) -> str:
    payload = text.strip()
    if not payload.startswith("```"):
        return payload
    lines = payload.splitlines()
    lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _parse_response(raw: str, chat_name: str) -> List[Message]:
    data = json.loads(_strip_code_fence(raw))
    raw_msgs = data.get("messages", [])
    assert isinstance(raw_msgs, list), "messages must be a list"

    messages: List[Message] = []
    for entry in raw_msgs:
        if not isinstance(entry, dict):
            continue
        msg_type = str(entry.get("type", "text"))
        _ok = {
            "text", "system", "link_card", "image", "video", "voice", "call",
            "unsupported", "other",
        }
        if msg_type not in _ok:
            msg_type = "text"
        messages.append(Message(
            chat_name=chat_name,
            sender=str(entry.get("sender", "UNKNOWN")),
            time=entry.get("time"),
            content=str(entry.get("content", "")),
            type=msg_type,
        ))
    return messages


def _extract_once(
    viewport_img: Image.Image,
    chat_name: str,
    model: str,
    *,
    prompt: str | None = None,
    timeout: float = 60.0,
    max_side_pixels: int = DEFAULT_MAX_SIDE_PIXELS,
) -> tuple[List[Message], Dict[str, Any]]:
    import litellm
    import sys

    ensure_openrouter_ascii_env()
    rgb = viewport_img.convert("RGB")
    scaled, orig_sz, final_sz = downscale_max_side(rgb, max_side_pixels)
    if orig_sz != final_sz:
        print(
            f"[read_visible] 缩小 {orig_sz[0]}×{orig_sz[1]} → {final_sz[0]}×{final_sz[1]} "
            f"(max_side={max_side_pixels}px)",
            flush=True,
            file=sys.stderr,
        )
    payload = pil_to_vision_payload(scaled)
    log_vision_timing(
        "read_visible",
        "encoded",
        model=model,
        format=payload.format_name,
        mime=payload.mime_type,
        width=payload.width,
        height=payload.height,
        bytes=payload.byte_count,
        b64_chars=payload.base64_char_count,
        encode_ms=round(payload.encode_seconds * 1000, 1),
        max_side_pixels=max_side_pixels,
    )
    if prompt is None:
        prompt = _build_prompt(chat_name)

    print(
        f"[read_visible] 调用 LLM model={model!r} timeout={timeout}s（等待远端，勿当作卡死）…",
        flush=True,
        file=sys.stderr,
    )
    litellm_model = litellm_openrouter_model(model)
    key = resolve_openrouter_api_key()
    h = openrouter_completion_headers(litellm_model, key)
    log_vision_timing(
        "read_visible",
        "request_start",
        model=litellm_model,
        format=payload.format_name,
        bytes=payload.byte_count,
        b64_chars=payload.base64_char_count,
        timeout_s=timeout,
    )
    request_started = time.perf_counter()
    response = litellm.completion(
        model=litellm_model,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": payload.data_url}},
                {"type": "text", "text": prompt},
            ],
        }],
        timeout=timeout,
        api_key=key,
        headers=h,
    )
    request_seconds = time.perf_counter() - request_started
    raw_text: str = response.choices[0].message.content or ""
    log_vision_timing(
        "read_visible",
        "completed",
        model=litellm_model,
        format=payload.format_name,
        bytes=payload.byte_count,
        request_ms=round(request_seconds * 1000, 1),
        response_chars=len(raw_text),
    )
    messages = _parse_response(raw_text, chat_name)
    meta = {
        "raw_text": raw_text,
        "model": litellm_model,
        "message_count": len(messages),
        "source_image_size": list(orig_sz),
        "llm_image_size": list(final_sz),
        "max_side_pixels": max_side_pixels,
        "vision_image_format": payload.format_name,
        "vision_image_mime": payload.mime_type,
        "vision_image_bytes": payload.byte_count,
        "vision_image_base64_chars": payload.base64_char_count,
        "vision_encode_seconds": payload.encode_seconds,
        "vision_request_seconds": request_seconds,
    }
    return messages, meta


def extract_viewport_messages(
    viewport_img: Image.Image,
    chat_name: str,
    model: str = DEFAULT_EXTRACT_MODEL,
    max_retries: int = 3,
) -> tuple[List[Message], Dict[str, Any]]:
    """从 viewport 截图中提取消息。

    返回 (messages, meta)。meta 包含 raw_text, model, message_count。
    """
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            return _extract_once(
                viewport_img, chat_name, model, prompt=None, timeout=60.0,
            )
        except Exception as exc:
            last_error = exc
            print(f"[read_visible] attempt {attempt + 1}/{max_retries} failed: {exc}")
            if attempt < max_retries - 1:
                continue
            raise
    assert last_error is not None
    raise last_error


def read_visible_messages(
    driver,
    chat_name: str,
    model: str = DEFAULT_EXTRACT_MODEL,
) -> tuple[List[Message], Image.Image, Dict[str, Any]]:
    """完整流程：截图 → 裁切 viewport → LLM 提取消息。

    参数：
      driver     — 已激活且已进入目标会话的 MacDriver
      chat_name  — 当前会话名称（直接注入，不让模型再识别）
      model      — vision LLM 模型标识

    返回 (messages, viewport_img, meta)。
    """
    window_img = driver.capture_wechat_window()
    viewport_img = crop_chat_viewport(window_img)
    messages, meta = extract_viewport_messages(viewport_img, chat_name, model=model)
    meta["window_size"] = window_img.size
    meta["viewport_size"] = viewport_img.size
    return messages, viewport_img, meta


def messages_to_dicts(messages: List[Message]) -> List[Dict[str, Any]]:
    """将 Message 列表转为可序列化的 dict 列表。"""
    return [
        {
            "chat_name": m.chat_name,
            "sender": m.sender,
            "time": m.time,
            "content": m.content,
            "type": m.type,
        }
        for m in messages
    ]
