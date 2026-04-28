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
    - `decode` returns the raw HunyuanOCR generated text.
    - `recognize` returns `OcrLine` items sorted by vertical position.
    - `bbox` is `(x1, y1, x2, y2)` in pixel coordinates relative to the input image.
"""

import difflib
import tempfile
from pathlib import Path

from PIL import Image

from shared.ocr_hunyuan_parser import (  # type: ignore[import-untyped]
    OcrLine,
    normalize_text,
    parse_hunyuan_lines,
)

_MODEL_NAME = "tencent/HunyuanOCR"
_PROMPT = "检测并识别图片中的文字，将文本坐标格式化输出。"


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
        device_map = "auto" if torch.cuda.is_available() else {"": "cpu"}
        self._model = HunYuanVLForConditionalGeneration.from_pretrained(
            _MODEL_NAME,
            attn_implementation="eager",
            dtype=torch.bfloat16,
            device_map=device_map,
        )
        print("[+] HunyuanOCR engine initialized.")
        return self._processor, self._model

    def decode(self, image: Image.Image) -> str:
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
            return _clean_repeated_substrings(output_text)
        finally:
            image_path.unlink(missing_ok=True)

    def recognize(self, image: Image.Image) -> list[OcrLine]:
        output_text = self.decode(image)
        rgb_image = image.convert("RGB")
        return parse_hunyuan_lines(output_text, rgb_image.width, rgb_image.height)

    def match_target(
        self,
        lines: list[OcrLine],
        target: str,
        min_sim: float = 0.55,
    ) -> OcrLine | None:
        norm_target = normalize_text(target)
        best: OcrLine | None = None
        best_score = -1.0
        for line in lines:
            norm_text = normalize_text(line.text)
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
