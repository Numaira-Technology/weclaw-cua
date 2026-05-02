"""Direct OpenAI-compatible VLM request helper for pre-encoded image payloads.

Usage:
    text = query_vlm_payload(config, prompt, payload, max_tokens=4096)

Input spec:
    - config: WeclawConfig with resolved llm provider, base URL, API key, and model.
    - payload: VisionImagePayload containing a data URL.

Output spec:
    - Returns stripped assistant text from chat.completions.
"""

from __future__ import annotations

import os

from config.weclaw_config import WeclawConfig
from shared.vision_image_codec import VisionImagePayload


def query_vlm_payload(
    config: WeclawConfig,
    prompt: str,
    payload: VisionImagePayload,
    max_tokens: int,
) -> str:
    from openai import OpenAI

    client = OpenAI(
        base_url=config.llm_base_url,
        api_key=config.llm_api_key,
        timeout=_http_timeout_sec(),
    )
    request_args: dict[str, object] = {
        "model": config.llm_wire_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": payload.data_url}},
                ],
            }
        ],
    }
    if _uses_openai_completion_tokens(config.llm_provider, config.llm_wire_model):
        request_args["max_completion_tokens"] = max_tokens
    else:
        request_args["max_tokens"] = max_tokens
    if not _is_openai_reasoning_model(config.llm_wire_model):
        request_args["temperature"] = 1 if config.llm_provider == "kimi" else 0
    response = client.chat.completions.create(**request_args)
    assert response.choices, "VLM returned no choices"
    message = response.choices[0].message
    assert message is not None and message.content is not None
    text = str(message.content).strip()
    assert text, "VLM returned empty content"
    return text


def _http_timeout_sec() -> float:
    raw = os.environ.get("WECLAW_VISION_HTTP_TIMEOUT_SEC", "").strip()
    if raw:
        value = float(raw)
        assert value >= 30.0
        return value
    return 360.0


def _uses_openai_completion_tokens(provider: str, model_name: str) -> bool:
    return provider == "openai" and _is_openai_reasoning_model(model_name)


def _is_openai_reasoning_model(model_name: str) -> bool:
    normalized = model_name.split("/", 1)[1] if model_name.startswith("openai/") else model_name
    return normalized.startswith(("gpt-5", "o3", "o4"))
