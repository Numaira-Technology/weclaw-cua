"""VLM screenshot image variant parsing.

Usage:
    variants = parse_vlm_image_variants(("webp:q90", "jpeg:q85"))

Input spec:
    - Variant specs: png, webp_lossless, webp[:qN], jpeg[:qN].
    - webm and webm_lossy are accepted as aliases for webp.

Output spec:
    - Returns VlmImageVariant values ready for encode_vision_image.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VlmImageVariant:
    name: str
    format_name: str
    quality_label: str
    webp_quality: int | None = None
    jpeg_quality: int | None = None


def default_vlm_image_variants() -> list[VlmImageVariant]:
    return [
        VlmImageVariant("png", "png", "default"),
        VlmImageVariant("webp_lossless", "webp_lossless", "lossless"),
        VlmImageVariant("webp_q95", "webp", "q95", webp_quality=95),
        VlmImageVariant("webp_q90", "webp", "q90", webp_quality=90),
        VlmImageVariant("webp_q85", "webp", "q85", webp_quality=85),
        VlmImageVariant("jpeg_q92", "jpeg", "q92", jpeg_quality=92),
        VlmImageVariant("jpeg_q85", "jpeg", "q85", jpeg_quality=85),
    ]


def parse_vlm_image_variants(raw_specs: tuple[str, ...]) -> list[VlmImageVariant]:
    if not raw_specs:
        return default_vlm_image_variants()
    return [_parse_variant(spec) for spec in raw_specs]


def _parse_variant(raw_spec: str) -> VlmImageVariant:
    spec = raw_spec.strip().lower().replace("-", "_")
    assert spec, "empty variant spec"
    base, _, quality_part = spec.partition(":")
    base = {
        "jpg": "jpeg",
        "webm": "webp",
        "webm_lossy": "webp",
        "webp_lossy": "webp",
        "webm_lossless": "webp_lossless",
    }.get(base, base)

    if base == "png":
        assert not quality_part, "png variant does not accept quality"
        return VlmImageVariant("png", "png", "default")
    if base == "webp_lossless":
        assert not quality_part, "webp_lossless variant does not accept quality"
        return VlmImageVariant("webp_lossless", "webp_lossless", "lossless")
    if base == "webp":
        quality = _parse_quality(quality_part or "q95")
        return VlmImageVariant(f"webp_q{quality}", "webp", f"q{quality}", webp_quality=quality)
    if base == "jpeg":
        quality = _parse_quality(quality_part or "q92")
        return VlmImageVariant(f"jpeg_q{quality}", "jpeg", f"q{quality}", jpeg_quality=quality)
    raise AssertionError("variant must be png, webp_lossless, webp[:qN], or jpeg[:qN]")


def _parse_quality(raw_quality: str) -> int:
    value = raw_quality.strip().lower()
    if value.startswith("q"):
        value = value[1:]
    quality = int(value)
    assert 1 <= quality <= 100, "quality must be between 1 and 100"
    return quality
