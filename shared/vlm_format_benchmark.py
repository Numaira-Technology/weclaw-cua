"""Live VLM benchmark for comparing screenshot image encodings.

Usage:
    results = run_vlm_format_benchmark(config, image, prompt, output_dir, variants)

Input spec:
    - config: loaded WeclawConfig with llm_provider, llm_wire_model, llm_base_url, and llm_api_key.
    - image: PIL screenshot captured once and reused for every encoding variant.
    - variants: VlmImageVariant values from shared.vlm_image_variants.

Output spec:
    - Writes encoded images and response text files under output_dir.
    - Returns result dicts containing size, timing, request metadata, and model response text.
"""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import as_completed
from dataclasses import asdict
from dataclasses import dataclass

from PIL import Image

from config.weclaw_config import WeclawConfig
from shared.vision_image_codec import VisionImagePayload
from shared.vision_image_codec import encode_vision_image
from shared.vision_image_codec import log_vision_timing
from shared.vlm_direct_client import query_vlm_payload
from shared.vlm_image_variants import VlmImageVariant


_EXTENSIONS = {
    "png": "png",
    "webp_lossless": "webp",
    "webp": "webp",
    "jpeg": "jpg",
}


@dataclass(frozen=True)
class VlmFormatBenchmarkResult:
    variant: str
    format_name: str
    quality: str
    mime_type: str
    width: int
    height: int
    bytes: int
    base64_chars: int
    png_ratio: float
    encode_ms: float
    request_ms: float
    total_ms: float
    response_chars: int
    image_file: str
    response_file: str
    response: str

def run_vlm_format_benchmark(
    *,
    config: WeclawConfig,
    image: Image.Image,
    prompt: str,
    output_dir: str,
    variants: list[VlmImageVariant],
    max_tokens: int,
    workers: int,
) -> list[dict]:
    assert config.llm_api_key, f"Set the API key for llm_provider={config.llm_provider}"
    assert config.llm_wire_model, "'llm_model' not found in config.json"
    assert prompt.strip(), "prompt must not be empty"
    assert variants, "at least one image variant is required"
    assert workers > 0, "workers must be > 0"
    os.makedirs(output_dir, exist_ok=True)

    png_payload = encode_vision_image(image, format_name="png")
    max_workers = min(workers, len(variants))
    results: list[tuple[int, VlmFormatBenchmarkResult]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(
                _run_one_variant,
                index=index,
                config=config,
                image=image.copy(),
                prompt=prompt,
                output_dir=output_dir,
                variant=variant,
                max_tokens=max_tokens,
                png_byte_count=png_payload.byte_count,
            )
            for index, variant in enumerate(variants)
        ]
        for future in as_completed(futures):
            results.append(future.result())

    return [asdict(result) for _, result in sorted(results, key=lambda item: item[0])]

def _run_one_variant(
    *,
    index: int,
    config: WeclawConfig,
    image: Image.Image,
    prompt: str,
    output_dir: str,
    variant: VlmImageVariant,
    max_tokens: int,
    png_byte_count: int,
) -> tuple[int, VlmFormatBenchmarkResult]:
    total_started = time.perf_counter()
    payload = encode_vision_image(
        image,
        format_name=variant.format_name,
        webp_quality=variant.webp_quality,
        jpeg_quality=variant.jpeg_quality,
    )
    image_path = _write_payload(output_dir, index, variant, payload)
    log_vision_timing(
        "vlm_format_benchmark",
        "encoded",
        provider=config.llm_provider,
        model=config.llm_wire_model,
        variant=variant.name,
        format=payload.format_name,
        mime=payload.mime_type,
        width=payload.width,
        height=payload.height,
        bytes=payload.byte_count,
        b64_chars=payload.base64_char_count,
        encode_ms=round(payload.encode_seconds * 1000, 1),
        max_tokens=max_tokens,
    )

    request_started = time.perf_counter()
    response = query_vlm_payload(config, prompt, payload, max_tokens)
    request_seconds = time.perf_counter() - request_started
    response_path = os.path.join(output_dir, f"{index:02d}_{variant.name}.response.txt")
    with open(response_path, "w", encoding="utf-8") as f:
        f.write(response)

    total_seconds = time.perf_counter() - total_started
    log_vision_timing(
        "vlm_format_benchmark",
        "completed",
        provider=config.llm_provider,
        model=config.llm_wire_model,
        variant=variant.name,
        format=payload.format_name,
        bytes=payload.byte_count,
        request_ms=round(request_seconds * 1000, 1),
        total_ms=round(total_seconds * 1000, 1),
        response_chars=len(response),
    )
    result = VlmFormatBenchmarkResult(
        variant=variant.name,
        format_name=payload.format_name,
        quality=variant.quality_label,
        mime_type=payload.mime_type,
        width=payload.width,
        height=payload.height,
        bytes=payload.byte_count,
        base64_chars=payload.base64_char_count,
        png_ratio=round(payload.byte_count / max(1, png_byte_count), 4),
        encode_ms=round(payload.encode_seconds * 1000, 1),
        request_ms=round(request_seconds * 1000, 1),
        total_ms=round(total_seconds * 1000, 1),
        response_chars=len(response),
        image_file=os.path.abspath(image_path),
        response_file=os.path.abspath(response_path),
        response=response,
    )
    return index, result


def _write_payload(
    output_dir: str,
    index: int,
    variant: VlmImageVariant,
    payload: VisionImagePayload,
) -> str:
    ext = _EXTENSIONS[payload.format_name]
    path = os.path.join(output_dir, f"{index:02d}_{variant.name}.{ext}")
    with open(path, "wb") as f:
        f.write(payload.raw_bytes)
    return path
