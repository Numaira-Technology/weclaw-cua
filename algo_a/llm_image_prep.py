"""送 vision LLM 前的图片准备：缩小、RGB、可配置格式 base64。"""

from __future__ import annotations

from pathlib import Path
from typing import Union

from PIL import Image

from shared.vision_image_codec import VisionImagePayload, encode_vision_image

DEFAULT_MAX_SIDE_PIXELS = 768


def downscale_max_side(
    img: Image.Image,
    max_side: int,
) -> tuple[Image.Image, tuple[int, int], tuple[int, int]]:
    """等比缩小，使 max(w,h) 不超过 max_side。max_side<=0 表示不缩小。"""
    w, h = img.size
    if max_side <= 0 or max(w, h) <= max_side:
        return img, (w, h), (w, h)
    scale = max_side / float(max(w, h))
    nw = max(1, int(round(w * scale)))
    nh = max(1, int(round(h * scale)))
    out = img.resize((nw, nh), Image.Resampling.LANCZOS)
    return out, (w, h), (nw, nh)


def pil_rgb_open(image: Union[Image.Image, Path, str]) -> Image.Image:
    if isinstance(image, Image.Image):
        return image.convert("RGB")
    return Image.open(Path(image)).convert("RGB")


def pil_to_vision_payload(pil: Image.Image) -> VisionImagePayload:
    return encode_vision_image(pil)


def pil_to_b64_png(pil: Image.Image) -> str:
    return encode_vision_image(pil, format_name="png").base64_data
