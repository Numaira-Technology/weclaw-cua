"""VLM image encoding and timing helpers.

Usage:
    from shared.vision_image_codec import encode_vision_image
    payload = encode_vision_image(image)

Input spec:
    - WECLAW_VISION_IMAGE_FORMAT: png, webp_lossless, webp, or jpeg.
    - WECLAW_VISION_WEBP_QUALITY: integer 1..100 for lossy webp, default 95.
    - WECLAW_VISION_JPEG_QUALITY: integer 1..100 for jpeg, default 92.
    - WECLAW_VISION_TIMING_LOG: 1/true/yes/on enables timing logs, enabled by default.

Output spec:
    - VisionImagePayload contains a data URL plus byte, base64, dimensions, and timing metadata.
"""

from __future__ import annotations

import base64
import io
import os
import time
from dataclasses import dataclass

from PIL import Image


_FORMAT_ALIASES = {
    "png": "png",
    "webp-lossless": "webp_lossless",
    "webp_lossless": "webp_lossless",
    "webp-lossy": "webp",
    "webp_lossy": "webp",
    "webp": "webp",
    "jpg": "jpeg",
    "jpeg": "jpeg",
}


@dataclass(frozen=True)
class VisionImagePayload:
    data_url: str
    base64_data: str
    raw_bytes: bytes
    mime_type: str
    format_name: str
    width: int
    height: int
    byte_count: int
    base64_char_count: int
    encode_seconds: float

    @property
    def payload_mib(self) -> float:
        return self.byte_count / (1024 * 1024)


def vision_timing_enabled() -> bool:
    raw = os.environ.get("WECLAW_VISION_TIMING_LOG", "1").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def selected_vision_image_format() -> str:
    raw = os.environ.get("WECLAW_VISION_IMAGE_FORMAT", "png").strip().lower()
    value = _FORMAT_ALIASES.get(raw)
    assert value, "WECLAW_VISION_IMAGE_FORMAT must be png, webp_lossless, webp, or jpeg"
    return value


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name, "").strip()
    value = int(raw) if raw else default
    assert minimum <= value <= maximum, f"{name} must be between {minimum} and {maximum}"
    return value


def _image_for_format(image: Image.Image, format_name: str) -> Image.Image:
    if format_name == "png" and image.mode in {"1", "L", "P", "RGB", "RGBA"}:
        return image
    if image.mode == "RGB":
        return image
    return image.convert("RGB")


def _save_image(image: Image.Image, format_name: str, buffer: io.BytesIO) -> str:
    if format_name == "png":
        image.save(buffer, format="PNG")
        return "image/png"
    if format_name == "webp_lossless":
        image.save(buffer, format="WEBP", lossless=True, quality=100, method=6)
        return "image/webp"
    if format_name == "webp":
        quality = _env_int("WECLAW_VISION_WEBP_QUALITY", 95, 1, 100)
        image.save(buffer, format="WEBP", quality=quality, method=6)
        return "image/webp"
    if format_name == "jpeg":
        quality = _env_int("WECLAW_VISION_JPEG_QUALITY", 92, 1, 100)
        image.save(buffer, format="JPEG", quality=quality, subsampling=0, optimize=True)
        return "image/jpeg"
    raise AssertionError(f"unsupported VLM image format: {format_name}")


def encode_vision_image(image: Image.Image, format_name: str | None = None) -> VisionImagePayload:
    assert isinstance(image, Image.Image)
    selected = format_name or selected_vision_image_format()
    prepared = _image_for_format(image, selected)
    started = time.perf_counter()
    buffer = io.BytesIO()
    mime_type = _save_image(prepared, selected, buffer)
    raw = buffer.getvalue()
    encoded = base64.b64encode(raw).decode("ascii")
    elapsed = time.perf_counter() - started
    return VisionImagePayload(
        data_url=f"data:{mime_type};base64,{encoded}",
        base64_data=encoded,
        raw_bytes=raw,
        mime_type=mime_type,
        format_name=selected,
        width=prepared.width,
        height=prepared.height,
        byte_count=len(raw),
        base64_char_count=len(encoded),
        encode_seconds=elapsed,
    )


def log_vision_timing(label: str, event: str, **values: object) -> None:
    if not vision_timing_enabled():
        return
    fields = " ".join(f"{key}={value}" for key, value in values.items())
    print(f"[vlm_timing] label={label} event={event} {fields}".rstrip())
