"""HunyuanOCR wrapper for precise text recognition in WeChat screenshots.

Usage:
    from shared.ocr_hunyuan import get_ocr_engine

    engine = get_ocr_engine()
    lines = engine.recognize(pil_image)
    hit = engine.match_target(lines, "周一例会")

Input spec:
    - `recognize` accepts a PIL Image and sends it to the local
      `tencent/HunyuanOCR` Transformers model.
    - HunyuanOCR is prompted for line-level text spotting with coordinates.

Output spec:
    - `recognize` returns `OcrLine` items sorted by vertical position.
    - `bbox` is `(x1, y1, x2, y2)` in pixel coordinates relative to the input image.
"""

from __future__ import annotations

import difflib
import re
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

_MODEL_NAME = "tencent/HunyuanOCR"
_PROMPT = "检测并识别图片中的文字，将文本坐标格式化输出。"
_REF_QUAD_RE = re.compile(
    r"<ref>(?P<text>.*?)</ref>\s*<quad>\s*"
    r"\((?P<x1>-?\d+(?:\.\d+)?),(?P<y1>-?\d+(?:\.\d+)?)\)\s*,\s*"
    r"\((?P<x2>-?\d+(?:\.\d+)?),(?P<y2>-?\d+(?:\.\d+)?)\)\s*</quad>",
    re.DOTALL,
)
_TEXT_BOX_RE = re.compile(
    r"(?P<text>[^\n<>()]+?)\s*"
    r"\((?P<x1>-?\d+(?:\.\d+)?),(?P<y1>-?\d+(?:\.\d+)?)\)\s*,\s*"
    r"\((?P<x2>-?\d+(?:\.\d+)?),(?P<y2>-?\d+(?:\.\d+)?)\)"
)


@dataclass
class OcrLine:
    """A single HunyuanOCR text line."""

    text: str
    bbox: tuple[int, int, int, int]
    conf: float = 1.0

    @property
    def center_y(self) -> int:
        return (self.bbox[1] + self.bbox[3]) // 2

    @property
    def center_x(self) -> int:
        return (self.bbox[0] + self.bbox[2]) // 2


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u2026", "...").replace("\u22ef", "...")
    return " ".join(text.split()).strip()


def _clean_repeated_substrings(text: str) -> str:
    n = len(text)
    if n < 8000:
        return text
    for length in range(2, n // 10 + 1):
        candidate = text[-length:]
        count = 0
        idx = n - length
        while idx >= 0 and text[idx : idx + length] == candidate:
            count += 1
            idx -= length
        if count >= 10:
            return text[: n - length * (count - 1)]
    return text


def _to_pixel_bbox(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    image_width: int,
    image_height: int,
) -> tuple[int, int, int, int]:
    scale_x = image_width / 1000.0 if max(abs(x1), abs(x2)) <= 1000 else 1.0
    scale_y = image_height / 1000.0 if max(abs(y1), abs(y2)) <= 1000 else 1.0
    left = int(round(min(x1, x2) * scale_x))
    top = int(round(min(y1, y2) * scale_y))
    right = int(round(max(x1, x2) * scale_x))
    bottom = int(round(max(y1, y2) * scale_y))
    return (
        max(0, min(left, image_width)),
        max(0, min(top, image_height)),
        max(0, min(right, image_width)),
        max(0, min(bottom, image_height)),
    )


def _parse_lines(text: str, image_width: int, image_height: int) -> list[OcrLine]:
    lines: list[OcrLine] = []
    for pattern in (_REF_QUAD_RE, _TEXT_BOX_RE):
        for match in pattern.finditer(text):
            line_text = _normalize(match.group("text"))
            if not line_text:
                continue
            bbox = _to_pixel_bbox(
                float(match.group("x1")),
                float(match.group("y1")),
                float(match.group("x2")),
                float(match.group("y2")),
                image_width,
                image_height,
            )
            if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
                continue
            lines.append(OcrLine(text=line_text, bbox=bbox))
        if lines:
            break
    lines.sort(key=lambda line: (line.center_y, line.bbox[0]))
    return lines


class HunyuanOcrEngine:
    """Lazy singleton wrapper around `tencent/HunyuanOCR`."""

    _instance: "HunyuanOcrEngine | None" = None

    def __new__(cls) -> "HunyuanOcrEngine":
        if cls._instance is None:
            obj = object.__new__(cls)
            obj._processor = None
            obj._model = None
            cls._instance = obj
        return cls._instance

    def _load(self):
        if self._processor is not None and self._model is not None:
            return self._processor, self._model
        import torch
        from transformers import AutoProcessor, HunYuanVLForConditionalGeneration

        print("[*] Initializing HunyuanOCR engine (first use)...")
        self._processor = AutoProcessor.from_pretrained(_MODEL_NAME, use_fast=False)
        self._model = HunYuanVLForConditionalGeneration.from_pretrained(
            _MODEL_NAME,
            attn_implementation="eager",
            dtype=torch.bfloat16,
            device_map="auto",
        )
        print("[+] HunyuanOCR engine initialized.")
        return self._processor, self._model

    def recognize(self, image: Image.Image) -> list[OcrLine]:
        processor, model = self._load()
        import torch

        rgb_image = image.convert("RGB")
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            image_path = Path(tmp.name)
        try:
            rgb_image.save(image_path)
            messages = [
                {"role": "system", "content": ""},
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": str(image_path)},
                        {"type": "text", "text": _PROMPT},
                    ],
                },
            ]
            prompt = processor.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
            inputs = processor(
                text=[prompt],
                images=rgb_image,
                padding=True,
                return_tensors="pt",
            )
            with torch.no_grad():
                device = next(model.parameters()).device
                inputs = inputs.to(device)
                generated_ids = model.generate(
                    **inputs,
                    max_new_tokens=16384,
                    do_sample=False,
                )
            input_ids = inputs.input_ids if "input_ids" in inputs else inputs.inputs
            generated_ids_trimmed = [
                out_ids[len(in_ids) :]
                for in_ids, out_ids in zip(input_ids, generated_ids)
            ]
            output_text = processor.batch_decode(
                generated_ids_trimmed,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
            )[0]
            output_text = _clean_repeated_substrings(output_text)
            return _parse_lines(output_text, rgb_image.width, rgb_image.height)
        finally:
            image_path.unlink(missing_ok=True)

    def match_target(
        self,
        lines: list[OcrLine],
        target: str,
        min_sim: float = 0.55,
    ) -> OcrLine | None:
        norm_target = _normalize(target)
        best: OcrLine | None = None
        best_score = -1.0
        for line in lines:
            norm_text = _normalize(line.text)
            if norm_text == norm_target:
                return line
            if norm_text.endswith("...") and norm_target.startswith(norm_text[:-3]):
                return line
            if norm_target.endswith("...") and norm_text.startswith(norm_target[:-3]):
                return line
            score = difflib.SequenceMatcher(None, norm_text, norm_target).ratio()
            if score > best_score:
                best_score = score
                best = line
        if best_score >= min_sim:
            return best
        return None


def get_ocr_engine() -> HunyuanOcrEngine:
    """Return the singleton HunyuanOCR engine, initializing it on first recognition."""
    return HunyuanOcrEngine()
