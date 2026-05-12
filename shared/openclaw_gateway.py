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

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import as_completed
from dataclasses import dataclass

from PIL import Image

from shared.vision_image_codec import encode_vision_image
from shared.vision_image_codec import log_vision_timing


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


def _image_path_data_url(path: str, label: str) -> str:
    with Image.open(path) as image:
        payload = encode_vision_image(image)
    log_vision_timing(
        label,
        "encoded",
        format=payload.format_name,
        mime=payload.mime_type,
        width=payload.width,
        height=payload.height,
        bytes=payload.byte_count,
        b64_chars=payload.base64_char_count,
        encode_ms=round(payload.encode_seconds * 1000, 1),
    )
    return payload.data_url


def _extra_headers(config: OpenClawGatewayConfig) -> dict[str, str] | None:
    if not config.backend_model:
        return None
    return {"x-openclaw-model": config.backend_model}


def _async_vlm_worker_count(workers: int | None) -> int:
    if workers is not None:
        assert workers >= 0, "workers must be >= 0"
        if workers > 0:
            return workers
    raw = os.environ.get("WECLAW_ASYNC_VLM_WORKERS", "").strip()
    if raw:
        value = int(raw)
        assert value >= 0, "WECLAW_ASYNC_VLM_WORKERS must be >= 0"
        return value
    return 2


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
    total_started = time.perf_counter()
    with Image.open(image_path) as image:
        payload = encode_vision_image(image)
    log_vision_timing(
        "openclaw_gateway",
        "encoded",
        format=payload.format_name,
        mime=payload.mime_type,
        width=payload.width,
        height=payload.height,
        bytes=payload.byte_count,
        b64_chars=payload.base64_char_count,
        encode_ms=round(payload.encode_seconds * 1000, 1),
        max_tokens=max_tokens,
    )
    log_vision_timing(
        "openclaw_gateway",
        "request_start",
        model=config.model,
        format=payload.format_name,
        bytes=payload.byte_count,
        b64_chars=payload.base64_char_count,
        max_tokens=max_tokens,
    )
    request_started = time.perf_counter()
    resp = client.chat.completions.create(
        model=config.model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": payload.data_url}},
                ],
            }
        ],
        max_tokens=max_tokens,
        extra_headers=_extra_headers(config),
    )
    request_seconds = time.perf_counter() - request_started
    assert resp.choices, "gateway returned no choices"
    msg = resp.choices[0].message
    assert msg is not None and msg.content is not None
    text = str(msg.content).strip()
    assert text, "gateway returned empty text"
    log_vision_timing(
        "openclaw_gateway",
        "completed",
        model=config.model,
        format=payload.format_name,
        bytes=payload.byte_count,
        request_ms=round(request_seconds * 1000, 1),
        total_ms=round((time.perf_counter() - total_started) * 1000, 1),
        response_chars=len(text),
        max_tokens=max_tokens,
    )
    return text


class OpenClawVisionBackend:
    """VisionBackend adapter that sends multimodal prompts through OpenClaw."""

    def __init__(self, config: OpenClawGatewayConfig) -> None:
        self.config = config

    def query(self, prompt: str, image, max_tokens: int = 2048) -> str | None:
        assert prompt
        assert max_tokens > 0
        total_started = time.perf_counter()
        payload = encode_vision_image(image)
        log_vision_timing(
            "openclaw_backend",
            "encoded",
            model=self.config.model,
            format=payload.format_name,
            mime=payload.mime_type,
            width=payload.width,
            height=payload.height,
            bytes=payload.byte_count,
            b64_chars=payload.base64_char_count,
            encode_ms=round(payload.encode_seconds * 1000, 1),
            max_tokens=max_tokens,
        )
        from openai import OpenAI

        log_vision_timing(
            "openclaw_backend",
            "request_start",
            model=self.config.model,
            format=payload.format_name,
            bytes=payload.byte_count,
            b64_chars=payload.base64_char_count,
            max_tokens=max_tokens,
        )
        client = OpenAI(base_url=self.config.base_url, api_key=self.config.api_key)
        request_started = time.perf_counter()
        resp = client.chat.completions.create(
            model=self.config.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": payload.data_url}},
                    ],
                }
            ],
            max_tokens=max_tokens,
            extra_headers=_extra_headers(self.config),
        )
        request_seconds = time.perf_counter() - request_started
        assert resp.choices, "gateway returned no choices"
        msg = resp.choices[0].message
        assert msg is not None and msg.content is not None
        text = str(msg.content).strip()
        assert text, "gateway returned empty text"
        log_vision_timing(
            "openclaw_backend",
            "completed",
            model=self.config.model,
            format=payload.format_name,
            bytes=payload.byte_count,
            request_ms=round(request_seconds * 1000, 1),
            total_ms=round((time.perf_counter() - total_started) * 1000, 1),
            response_chars=len(text),
        )
        return text


def fill_stepwise_responses(
    *,
    work_dir: str,
    config: OpenClawGatewayConfig,
    skip_existing: bool = False,
    force: bool = False,
    workers: int | None = None,
) -> dict:
    manifest_path = os.path.join(work_dir, "manifest.json")
    assert os.path.isfile(manifest_path), f"manifest not found: {manifest_path}"
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    tasks = manifest.get("tasks", [])
    assert isinstance(tasks, list) and tasks, "manifest has no tasks"

    skipped = 0
    pending_tasks = []
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
        pending_tasks.append((step_id, img_path, prompt_text, out_path, max_tokens))

    worker_count = _async_vlm_worker_count(workers)
    if not pending_tasks:
        return {
            "total_tasks": len(tasks),
            "responses_written": 0,
            "responses_skipped": skipped,
            "workers": 0,
        }
    if worker_count <= 0:
        written = 0
        for step_id, img_path, prompt_text, out_path, max_tokens in pending_tasks:
            _fill_one_stepwise_response(
                config=config,
                step_id=step_id,
                img_path=img_path,
                prompt_text=prompt_text,
                out_path=out_path,
                max_tokens=max_tokens,
            )
            written += 1
        return {
            "total_tasks": len(tasks),
            "responses_written": written,
            "responses_skipped": skipped,
            "workers": worker_count,
        }

    max_workers = min(worker_count, len(pending_tasks))
    written = 0
    with ThreadPoolExecutor(
        max_workers=max_workers,
        thread_name_prefix="weclaw-openclaw",
    ) as pool:
        futures = [
            pool.submit(
                _fill_one_stepwise_response,
                config=config,
                step_id=step_id,
                img_path=img_path,
                prompt_text=prompt_text,
                out_path=out_path,
                max_tokens=max_tokens,
            )
            for step_id, img_path, prompt_text, out_path, max_tokens in pending_tasks
        ]
        for future in as_completed(futures):
            future.result()
            written += 1

    return {
        "total_tasks": len(tasks),
        "responses_written": written,
        "responses_skipped": skipped,
        "workers": max_workers,
    }


def _fill_one_stepwise_response(
    *,
    config: OpenClawGatewayConfig,
    step_id: str,
    img_path: str,
    prompt_text: str,
    out_path: str,
    max_tokens: int,
) -> None:
    text = gateway_chat_vision(
        config=config,
        prompt=prompt_text,
        image_path=img_path,
        max_tokens=max_tokens,
    )
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"[ok] {step_id} -> {os.path.basename(out_path)}")
