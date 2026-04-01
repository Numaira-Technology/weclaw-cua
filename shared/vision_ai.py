"""OpenRouter vision client for screenshot + prompt queries.

Usage:
    VisionAI().query(prompt, image)
    Optional env: WECLAW_VISION_HTTP_TIMEOUT_SEC (default 360) for slow multimodal calls.
"""

import base64
import io
import json
import os
import time
from typing import Tuple

import openai
from openai import APITimeoutError
from PIL import Image


def _load_ai_config(config_path: str = "config/config.json") -> Tuple[str, str]:
    api_key = (
        os.environ.get("OPENROUTER_API_KEY", "").strip()
        or os.environ.get("LITELLM_API_KEY", "").strip()
    )
    model_name = ""
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
        if not api_key:
            api_key = config.get("openrouter_api_key", "").strip()
        model_name = config.get("llm_model", "").strip()
    assert api_key, "Set OPENROUTER_API_KEY (or LITELLM_API_KEY) or openrouter_api_key in config.json"
    assert model_name, "'llm_model' not found in config.json"
    return api_key, model_name


def _http_timeout_sec() -> float:
    raw = os.environ.get("WECLAW_VISION_HTTP_TIMEOUT_SEC", "").strip()
    if raw:
        v = float(raw)
        assert v >= 30.0
        return v
    return 360.0


class VisionAI:
    """Singleton OpenRouter multimodal client."""

    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            print("[*] Initializing Vision AI model via OpenRouter...")
            cls._instance = super(VisionAI, cls).__new__(cls)
            api_key, model_name = _load_ai_config()
            t = _http_timeout_sec()
            cls._instance.client = openai.OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=api_key,
                timeout=t,
            )
            cls._instance.http_timeout_sec = t
            cls._instance.model_name = model_name
            print(
                f"[+] Vision AI client for model '{model_name}' initialized (HTTP timeout {t}s)."
            )
        return cls._instance

    def query(self, prompt: str, image: Image.Image, max_tokens: int = 2048) -> str | None:
        assert self.client
        assert max_tokens > 0
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        base64_image = base64.b64encode(buffered.getvalue()).decode("utf-8")
        approx_mb = len(base64_image) * 0.75 / (1024 * 1024)
        max_retries = 3
        for attempt in range(max_retries):
            print(
                f"[*] Sending query to Vision AI via OpenRouter... (Attempt {attempt + 1}/{max_retries})"
            )
            print(
                f"[*] Image payload ~{approx_mb:.1f} MiB; first byte may take 1–6 min (timeout {self.http_timeout_sec:.0f}s)."
            )
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
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
                    max_tokens=max_tokens,
                )
            except APITimeoutError as e:
                print(
                    f"[!] OpenRouter request timed out after {self.http_timeout_sec:.0f}s: {e}"
                )
                if attempt + 1 < max_retries:
                    time.sleep(2)
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
