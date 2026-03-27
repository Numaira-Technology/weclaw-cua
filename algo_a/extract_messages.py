"""聊天长图 → vision LLM → JSON（见 EXTRACT_PROMPT 与 _parse_payload）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Union

from PIL import Image

from algo_a.llm_image_prep import (
    DEFAULT_MAX_SIDE_PIXELS,
    downscale_max_side,
    pil_rgb_open,
    pil_to_b64_png,
)
from algo_a.llm_openrouter_headers import headers_for_model


EXTRACT_PROMPT = (
    "Extract visible WeChat messages from this long chat screenshot and return JSON only.\n\n"
    "Rules:\n"
    "1. Follow the JSON schema exactly.\n"
    "2. Keep messages in top-to-bottom order.\n"
    "3. For each message, extract: sender, time, content, type.\n"
    '4. If time is not explicitly visible, use null.\n'
    '5. If sender is unclear, use "UNKNOWN".\n'
    '6. For system notices or date separators, use sender="SYSTEM", type="system".\n'
    '7. For link/job/share/mini-program cards, extract visible title/summary into content, type="link_card".\n'
    "8. Do not invent hidden or cut-off content; only extract what is visible.\n\n"
    "JSON schema:\n"
    "{\n"
    '  "messages": [\n'
    "    {\n"
    '      "sender": "string",\n'
    '      "time": "string|null",\n'
    '      "content": "string",\n'
    '      "type": "text|system|link_card|other"\n'
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

    pil = pil_rgb_open(image)
    scaled, orig_sz, final_sz = downscale_max_side(pil, max_side_pixels)
    if orig_sz != final_sz:
        print(
            f"[extract_messages] 缩小 {orig_sz[0]}×{orig_sz[1]} → {final_sz[0]}×{final_sz[1]} "
            f"(max_side={max_side_pixels}px)",
            flush=True,
            file=sys.stderr,
        )
    print(
        f"[extract_messages] 请求 LLM（{final_sz[0]}×{final_sz[1]}px, timeout={timeout}s）…",
        flush=True,
        file=sys.stderr,
    )
    image_b64 = pil_to_b64_png(scaled)
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                {"type": "text", "text": EXTRACT_PROMPT},
            ],
        }
    ]
    h = headers_for_model(model)
    response = litellm.completion(
        model=model,
        messages=messages,
        timeout=timeout,
        **({"headers": h} if h else {}),
    )
    raw: str = response.choices[0].message.content or ""
    raw = _sanitize_surrogates(raw)
    parsed = _parse_payload(raw)
    parsed["raw_text"] = raw
    parsed["model"] = model
    parsed["source_image_size"] = list(orig_sz)
    parsed["llm_image_size"] = list(final_sz)
    parsed["max_side_pixels"] = max_side_pixels
    return parsed


# 与 wechat-admin-bot-main/modules/whole_pic_message_extractor.py 默认一致
DEFAULT_EXTRACT_MODEL = "openrouter/google/gemini-3-flash-preview"


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
