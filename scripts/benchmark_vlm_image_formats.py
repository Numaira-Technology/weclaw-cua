"""Benchmark VLM image encodings for screenshot payload tests.

Usage:
    python scripts/benchmark_vlm_image_formats.py image1.png image2.png

Input spec:
    - Positional arguments are image paths readable by Pillow.
    - The script tests png, webp_lossless, webp q95, webp q90, jpeg q92, and jpeg q85.

Output spec:
    - Prints CSV rows with format, quality, dimensions, byte size, base64 size, ratio, and encode time.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.vision_image_codec import encode_vision_image


def _set_quality_env(webp_quality: int | None, jpeg_quality: int | None) -> None:
    if webp_quality is None:
        os.environ.pop("WECLAW_VISION_WEBP_QUALITY", None)
    else:
        os.environ["WECLAW_VISION_WEBP_QUALITY"] = str(webp_quality)
    if jpeg_quality is None:
        os.environ.pop("WECLAW_VISION_JPEG_QUALITY", None)
    else:
        os.environ["WECLAW_VISION_JPEG_QUALITY"] = str(jpeg_quality)


def _variants() -> list[tuple[str, str, int | None, int | None]]:
    return [
        ("png", "default", None, None),
        ("webp_lossless", "lossless", None, None),
        ("webp", "q95", 95, None),
        ("webp", "q90", 90, None),
        ("jpeg", "q92", None, 92),
        ("jpeg", "q85", None, 85),
    ]


def benchmark_image(path: Path) -> None:
    with Image.open(path) as image:
        png_payload = encode_vision_image(image, format_name="png")
        for format_name, quality_label, webp_quality, jpeg_quality in _variants():
            _set_quality_env(webp_quality, jpeg_quality)
            payload = encode_vision_image(image, format_name=format_name)
            ratio = payload.byte_count / max(1, png_payload.byte_count)
            print(
                ",".join([
                    str(path),
                    format_name,
                    quality_label,
                    str(payload.width),
                    str(payload.height),
                    str(payload.byte_count),
                    str(payload.base64_char_count),
                    f"{ratio:.4f}",
                    f"{payload.encode_seconds * 1000:.1f}",
                    payload.mime_type,
                ])
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark VLM screenshot image formats.")
    parser.add_argument("images", nargs="+", type=Path)
    args = parser.parse_args()
    print("path,format,quality,width,height,bytes,base64_chars,png_ratio,encode_ms,mime")
    for path in args.images:
        assert path.is_file(), f"image not found: {path}"
        benchmark_image(path)


if __name__ == "__main__":
    main()
