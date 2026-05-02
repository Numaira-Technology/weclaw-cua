"""聊天长图 → vision LLM → JSON（见 EXTRACT_PROMPT 与 _parse_payload）。"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Union

from PIL import Image

from algo_a.llm_image_prep import (
    DEFAULT_MAX_SIDE_PIXELS,
    downscale_max_side,
    pil_rgb_open,
    pil_to_vision_payload,
)
from algo_a.llm_openrouter_headers import ensure_openrouter_ascii_env, openrouter_completion_headers
from shared.openrouter_api_key import resolve_openrouter_api_key
from shared.openrouter_litellm_model import litellm_openrouter_model
from shared.vision_image_codec import log_vision_timing


EXTRACT_PROMPT = (
    "Extract visible WeChat messages from this long chat screenshot and return JSON only.\n\n"
    "Rules:\n"
    "1. Follow the JSON schema exactly.\n"
    "2. Keep messages in top-to-bottom order.\n"
    "3. For each message, extract: sender, time, content, type.\n"
    '4. If time is not explicitly visible, use null.\n'
    '5. If sender is unclear, use "UNKNOWN".\n'
    '6. Do NOT output standalone date/time separator rows as messages. For real '
    'system notices (join/leave/recall), use sender="SYSTEM", type="system".\n'
    '7. For link/share/mini-program cards, type="link_card" with visible title/summary in content. '
    'For image-only bubbles without caption, type="image", content="[图片]". '
    'For video bubbles, type="video", content="[视频]" (optional caption after a space). '
    'For voice bubbles, type="voice", one line "[语音]" plus duration; do not emit a second line '
    'that is only duration. '
    'For file bubbles not fully readable, type="unsupported", content "[文件] name". '
    'For call status rows (Canceled, Missed, 未接听, 通话时长), type="call".\n'
    '7r. Reply/quote bubbles: one message, type="text", merge quoted block and reply in content.\n'
    "8. Do not invent hidden or cut-off content; only extract what is visible.\n"
    "9. Never emit a message whose content is only a timestamp or date line.\n"
    "10. If the same sender posts nearly identical duplicate text, output one message.\n\n"
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
    '  "extraction_confidence": "high|medium|low",\n'
    '  "boundary_stability": "stable|unstable"\n'
    "}"
)


def _sanitize_surrogates(text: str) -> str:
    """对齐 run_wechat_removal：去掉代理对字符，避免 JSON/写盘 UTF-8 报错。"""
    return text.encode("utf-8", errors="surrogatepass").decode("utf-8", errors="replace")


def _strip_code_fence(text: str) -> str:
    payload = text.strip()
    if not payload.startswith("```"):
        return payload
    lines = payload.splitlines()
    lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _parse_payload(text: str) -> Dict[str, Any]:
    payload = json.loads(_strip_code_fence(text))
    messages = payload.get("messages", [])
    assert isinstance(messages, list), "messages must be a list"
    normalized: List[Dict[str, Any]] = []
    for entry in messages:
        if not isinstance(entry, dict):
            continue
        normalized.append({
            "sender": str(entry.get("sender", "UNKNOWN")),
            "time": entry.get("time"),
            "content": str(entry.get("content", "")),
            "type": str(entry.get("type", "other")),
        })
    confidence = str(payload.get("extraction_confidence", "low")).lower()
    boundary = str(payload.get("boundary_stability", "unstable")).lower()
    if confidence not in {"high", "medium", "low"}:
        confidence = "low"
    if boundary not in {"stable", "unstable"}:
        boundary = "unstable"
    return {
        "messages": normalized,
        "extraction_confidence": confidence,
        "boundary_stability": boundary,
    }


def _extract_once(
    image: Union[Image.Image, Path, str],
    model: str,
    timeout: float = 120.0,
    max_side_pixels: int = DEFAULT_MAX_SIDE_PIXELS,
) -> Dict[str, Any]:
    import sys
    import litellm

    total_started = time.perf_counter()
    ensure_openrouter_ascii_env()
    pil = pil_rgb_open(image)
    scaled, orig_sz, final_sz = downscale_max_side(pil, max_side_pixels)
    if orig_sz != final_sz:
        print(
            f"[extract_messages] 缩小 {orig_sz[0]}×{orig_sz[1]} → {final_sz[0]}×{final_sz[1]} "
            f"(max_side={max_side_pixels}px)",
            flush=True,
            file=sys.stderr,
        )
    payload = pil_to_vision_payload(scaled)
    log_vision_timing(
        "extract_messages",
        "encoded",
        format=payload.format_name,
        mime=payload.mime_type,
        width=payload.width,
        height=payload.height,
        bytes=payload.byte_count,
        b64_chars=payload.base64_char_count,
        encode_ms=round(payload.encode_seconds * 1000, 1),
        max_side=max_side_pixels,
    )
    print(
        f"[extract_messages] 请求 LLM（{final_sz[0]}×{final_sz[1]}px, "
        f"format={payload.format_name}, payload={payload.payload_mib:.1f} MiB, timeout={timeout}s）…",
        flush=True,
        file=sys.stderr,
    )
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": payload.data_url}},
                {"type": "text", "text": EXTRACT_PROMPT},
            ],
        }
    ]
    litellm_model = litellm_openrouter_model(model)
    key = resolve_openrouter_api_key()
    h = openrouter_completion_headers(litellm_model, key)
    log_vision_timing(
        "extract_messages",
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
        messages=messages,
        timeout=timeout,
        api_key=key,
        headers=h,
    )
    request_seconds = time.perf_counter() - request_started
    raw: str = response.choices[0].message.content or ""
    raw = _sanitize_surrogates(raw)
    log_vision_timing(
        "extract_messages",
        "completed",
        model=litellm_model,
        format=payload.format_name,
        bytes=payload.byte_count,
        request_ms=round(request_seconds * 1000, 1),
        total_ms=round((time.perf_counter() - total_started) * 1000, 1),
        response_chars=len(raw),
    )
    parsed = _parse_payload(raw)
    parsed["raw_text"] = raw
    parsed["model"] = litellm_model
    parsed["source_image_size"] = list(orig_sz)
    parsed["llm_image_size"] = list(final_sz)
    parsed["max_side_pixels"] = max_side_pixels
    parsed["vision_image_format"] = payload.format_name
    parsed["vision_image_bytes"] = payload.byte_count
    parsed["vision_image_encode_seconds"] = payload.encode_seconds
    return parsed


DEFAULT_EXTRACT_MODEL = "google/gemini-3-flash-preview"


def extract_messages(
    image: Union[Image.Image, Path, str],
    model: str = DEFAULT_EXTRACT_MODEL,
    max_retries: int = 3,
    max_side_pixels: int = DEFAULT_MAX_SIDE_PIXELS,
) -> Dict[str, Any]:
    """长图或路径；max_side_pixels<=0 表示不缩小。"""
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            return _extract_once(image, model, max_side_pixels=max_side_pixels)
        except Exception as exc:
            last_error = exc
            print(f"[extract_messages] attempt {attempt + 1}/{max_retries} failed: {exc}")
            if attempt < max_retries - 1:
                continue
            raise
    assert last_error is not None
    raise last_error


def extract_and_save(
    image: Union[Image.Image, Path, str],
    output_path: Union[str, Path],
    model: str = DEFAULT_EXTRACT_MODEL,
    max_side_pixels: int = DEFAULT_MAX_SIDE_PIXELS,
) -> Dict[str, Any]:
    result = extract_messages(image, model=model, max_side_pixels=max_side_pixels)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    save_data = {
        "messages": result["messages"],
        "extraction_confidence": result["extraction_confidence"],
        "boundary_stability": result["boundary_stability"],
        "model": result["model"],
        "source_image_size": result.get("source_image_size"),
        "llm_image_size": result.get("llm_image_size"),
        "max_side_pixels": result.get("max_side_pixels"),
    }
    output.write_text(json.dumps(save_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[extract_messages] saved {len(result['messages'])} messages → {output}")
    return result
