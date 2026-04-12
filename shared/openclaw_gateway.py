"""OpenClaw gateway client and stepwise response filler.

Usage:
    cfg = OpenClawGatewayConfig.from_env_or_local()
    text = gateway_chat_text(cfg, "Hello")
    fill_stepwise_responses(work_dir="output/work", config=cfg)

Input spec:
    - OPENCLAW_GATEWAY_URL: optional full base URL ending with /v1
    - OPENCLAW_API_KEY: optional bearer token; falls back to ~/.openclaw/openclaw.json
    - OPENCLAW_MODEL: optional OpenClaw agent target (default: openclaw/default)
    - OPENCLAW_BACKEND_MODEL: optional x-openclaw-model override

Output spec:
    - gateway_chat_* returns assistant text content.
    - fill_stepwise_responses writes step_*.response.txt files and returns summary dict.
"""

from __future__ import annotations

import base64
import io
import json
import os
from dataclasses import dataclass


@dataclass
class OpenClawGatewayConfig:
    base_url: str
    api_key: str
    model: str
    backend_model: str | None = None

    @classmethod
    def from_env_or_local(cls) -> "OpenClawGatewayConfig":
        base_url = os.environ.get("OPENCLAW_GATEWAY_URL", "").strip()
        model = os.environ.get("OPENCLAW_MODEL", "").strip() or "openclaw/default"
        api_key = os.environ.get("OPENCLAW_API_KEY", "").strip()
        backend_model = os.environ.get("OPENCLAW_BACKEND_MODEL", "").strip() or None
        if base_url and api_key:
            return cls(
                base_url=base_url.rstrip("/"),
                api_key=api_key,
                model=model,
                backend_model=backend_model,
            )

        config_path = os.path.expanduser("~/.openclaw/openclaw.json")
        assert os.path.isfile(config_path), (
            "Set OPENCLAW_GATEWAY_URL / OPENCLAW_API_KEY or create ~/.openclaw/openclaw.json"
        )
        with open(config_path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        gateway = raw.get("gateway", {})
        auth = gateway.get("auth", {})
        port = int(gateway.get("port", 18789))
        bind = str(gateway.get("bind", "127.0.0.1") or "127.0.0.1").strip()
        if bind == "loopback":
            bind = "127.0.0.1"
        if not base_url:
            base_url = f"http://{bind}:{port}/v1"
        if not api_key:
            mode = str(auth.get("mode", "") or "").strip()
            if mode == "token":
                api_key = str(auth.get("token", "") or "").strip()
            elif mode == "password":
                api_key = str(auth.get("password", "") or "").strip()
            elif mode == "none":
                api_key = "openclaw-local"
        assert api_key, "Could not resolve OpenClaw gateway bearer token"
        return cls(
            base_url=base_url.rstrip("/"),
            api_key=api_key,
            model=model,
            backend_model=backend_model,
        )


def _b64_data_url_png(path: str) -> str:
    with open(path, "rb") as f:
        raw = f.read()
    b64 = base64.standard_b64encode(raw).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _extra_headers(config: OpenClawGatewayConfig) -> dict[str, str] | None:
    if not config.backend_model:
        return None
    return {"x-openclaw-model": config.backend_model}


def gateway_chat_text(config: OpenClawGatewayConfig, prompt: str, max_tokens: int = 4096) -> str:
    from openai import OpenAI

    client = OpenAI(base_url=config.base_url, api_key=config.api_key)
    resp = client.chat.completions.create(
        model=config.model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        extra_headers=_extra_headers(config),
    )
    assert resp.choices, "gateway returned no choices"
    msg = resp.choices[0].message
    assert msg is not None and msg.content is not None
    text = str(msg.content).strip()
    assert text, "gateway returned empty text"
    return text


def gateway_chat_vision(
    config: OpenClawGatewayConfig,
    prompt: str,
    image_path: str,
    max_tokens: int,
) -> str:
    from openai import OpenAI

    client = OpenAI(base_url=config.base_url, api_key=config.api_key)
    resp = client.chat.completions.create(
        model=config.model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": _b64_data_url_png(image_path)}},
                ],
            }
        ],
        max_tokens=max_tokens,
        extra_headers=_extra_headers(config),
    )
    assert resp.choices, "gateway returned no choices"
    msg = resp.choices[0].message
    assert msg is not None and msg.content is not None
    text = str(msg.content).strip()
    assert text, "gateway returned empty text"
    return text


class OpenClawVisionBackend:
    """VisionBackend adapter that sends multimodal prompts through OpenClaw."""

    def __init__(self, config: OpenClawGatewayConfig) -> None:
        self.config = config

    def query(self, prompt: str, image, max_tokens: int = 2048) -> str | None:
        assert prompt
        assert max_tokens > 0
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        raw = buffered.getvalue()
        b64 = base64.standard_b64encode(raw).decode("ascii")
        from openai import OpenAI

        client = OpenAI(base_url=self.config.base_url, api_key=self.config.api_key)
        resp = client.chat.completions.create(
            model=self.config.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                    ],
                }
            ],
            max_tokens=max_tokens,
            extra_headers=_extra_headers(self.config),
        )
        assert resp.choices, "gateway returned no choices"
        msg = resp.choices[0].message
        assert msg is not None and msg.content is not None
        text = str(msg.content).strip()
        assert text, "gateway returned empty text"
        return text


def fill_stepwise_responses(
    *,
    work_dir: str,
    config: OpenClawGatewayConfig,
    skip_existing: bool = False,
    force: bool = False,
) -> dict:
    manifest_path = os.path.join(work_dir, "manifest.json")
    assert os.path.isfile(manifest_path), f"manifest not found: {manifest_path}"
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    tasks = manifest.get("tasks", [])
    assert isinstance(tasks, list) and tasks, "manifest has no tasks"

    written = 0
    skipped = 0
    for task in tasks:
        step_id = task["step_id"]
        img_path = os.path.join(work_dir, task["image"])
        prompt_path = os.path.join(work_dir, task["prompt_file"])
        out_path = os.path.join(work_dir, task["response_file"])
        max_tokens = int(task.get("max_tokens", 4096))
        assert os.path.isfile(img_path), f"missing image: {img_path}"
        assert os.path.isfile(prompt_path), f"missing prompt: {prompt_path}"

        if os.path.isfile(out_path):
            with open(out_path, "r", encoding="utf-8") as f:
                has_text = bool(f.read().strip())
            if has_text and (skip_existing or not force):
                skipped += 1
                continue

        with open(prompt_path, "r", encoding="utf-8") as f:
            prompt_text = f.read()
        assert prompt_text.strip(), f"empty prompt: {prompt_path}"
        text = gateway_chat_vision(
            config=config,
            prompt=prompt_text,
            image_path=img_path,
            max_tokens=max_tokens,
        )
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text)
        written += 1
        print(f"[ok] {step_id} -> {os.path.basename(out_path)}")

    return {
        "total_tasks": len(tasks),
        "responses_written": written,
        "responses_skipped": skipped,
    }
