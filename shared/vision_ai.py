"""OpenAI-compatible vision client for screenshot + prompt queries.

Usage:
    VisionAI().query(prompt, image)
    Optional env: WECLAW_VISION_HTTP_TIMEOUT_SEC (default 360) for slow multimodal calls.
"""

import base64
import io
import os
import time

from openai import APITimeoutError
from openai import OpenAI
from openai import RateLimitError
from PIL import Image

from config.weclaw_config import load_config


def _load_ai_config(config_path: str = "config/config.json") -> tuple[str, str, str, str]:
    config = load_config(config_path)
    assert config.llm_api_key, (
        f"Set the API key for llm_provider={config.llm_provider}"
    )
    assert config.llm_wire_model, "'llm_model' not found in config.json"
    return (
        config.llm_provider,
        config.llm_api_key,
        config.llm_wire_model,
        config.llm_base_url,
    )


def _http_timeout_sec() -> float:
    raw = os.environ.get("WECLAW_VISION_HTTP_TIMEOUT_SEC", "").strip()
    if raw:
        v = float(raw)
        assert v >= 30.0
        return v
    return 360.0


def _is_openai_reasoning_model(model_name: str) -> bool:
    normalized = model_name.split("/", 1)[1] if model_name.startswith("openai/") else model_name
    return normalized.startswith(("gpt-5", "o3", "o4"))


def _temperature_for_provider(provider: str) -> int:
    if provider == "kimi":
        return 1
    return 0


def _small_ui_max_side() -> int:
    raw = os.environ.get("WECLAW_VISION_UI_MAX_SIDE_PX", "").strip()
    if not raw:
        return 1280
    value = int(raw)
    assert value >= 320
    return value


def _resize_for_small_ui_task(image: Image.Image, max_tokens: int) -> Image.Image:
    if max_tokens > 2048:
        return image
    max_side = _small_ui_max_side()
    width, height = image.size
    current_max = max(width, height)
    if current_max <= max_side:
        return image
    scale = max_side / float(current_max)
    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return image.resize(new_size, Image.Resampling.LANCZOS)


def _rate_limit_retry_delay(exc: RateLimitError) -> float:
    response = getattr(exc, "response", None)
    if response is not None:
        retry_after = response.headers.get("retry-after")
        if retry_after:
            try:
                return max(1.0, float(retry_after))
            except ValueError:
                pass
    return 2.0


class VisionAI:
    """Singleton OpenAI-compatible multimodal client."""

    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            print("[*] Initializing Vision AI model...")
            cls._instance = super(VisionAI, cls).__new__(cls)
            provider, api_key, model_name, base_url = _load_ai_config()
            t = _http_timeout_sec()
            cls._instance.client = OpenAI(
                base_url=base_url,
                api_key=api_key,
                timeout=t,
            )
            cls._instance.provider = provider
            cls._instance.http_timeout_sec = t
            cls._instance.model_name = model_name
            print(
                f"[+] Vision AI client via {provider} for model '{model_name}' initialized (HTTP timeout {t}s)."
            )
        return cls._instance

    def query(self, prompt: str, image: Image.Image, max_tokens: int = 2048) -> str | None:
        assert self.client
        assert max_tokens > 0
        image_to_send = _resize_for_small_ui_task(image, max_tokens)
        buffered = io.BytesIO()
        image_to_send.save(buffered, format="PNG")
        base64_image = base64.b64encode(buffered.getvalue()).decode("utf-8")
        approx_mb = len(base64_image) * 0.75 / (1024 * 1024)
        max_retries = 3
        for attempt in range(max_retries):
            print(
                f"[*] Sending query to Vision AI via {self.provider}... (Attempt {attempt + 1}/{max_retries})"
            )
            print(
                f"[*] Image payload ~{approx_mb:.1f} MiB ({image_to_send.width}x{image_to_send.height}); "
                f"first byte may take 1–6 min (timeout {self.http_timeout_sec:.0f}s)."
            )
            try:
                uses_openai_reasoning_model = _is_openai_reasoning_model(self.model_name)
                uses_openai_completion_tokens = self.provider == "openai" and uses_openai_reasoning_model
                request_args = {
                    "model": self.model_name,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{base64_image}"
                                    },
                                },
                            ],
                        }
                    ],
                }
                if uses_openai_completion_tokens:
                    request_args["max_completion_tokens"] = max_tokens
                else:
                    request_args["max_tokens"] = max_tokens
                if not uses_openai_reasoning_model:
                    request_args["temperature"] = _temperature_for_provider(self.provider)
                response = self.client.chat.completions.create(**request_args)
            except APITimeoutError as e:
                print(
                    f"[!] Vision AI request timed out after {self.http_timeout_sec:.0f}s: {e}"
                )
                if attempt + 1 < max_retries:
                    time.sleep(2)
                continue
            except RateLimitError as e:
                if attempt + 1 >= max_retries:
                    raise
                delay = _rate_limit_retry_delay(e)
                print(f"[!] Vision AI rate limited; retrying after {delay:.1f}s: {e}")
                time.sleep(delay)
                continue
            print("[+] Received response from Vision AI.")
            if not response.choices:
                time.sleep(1)
                continue
            content = response.choices[0].message.content
            if not content:
                image.save("debug_empty_response_capture.png")
                time.sleep(1)
                continue
            return content
        return None
