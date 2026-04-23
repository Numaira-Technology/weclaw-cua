"""Hunyuan OCR engine for Windows sidebar OCR flow."""

from __future__ import annotations

import json
import re

import numpy as np
from PIL import Image

from shared.ocr_paddle import OcrLine, PaddleOcrEngine


class HunyuanOcrEngine(PaddleOcrEngine):
    """Singleton OCR engine backed by local tencent/HunyuanOCR."""

    _instance: "HunyuanOcrEngine | None" = None

    def __new__(cls) -> "HunyuanOcrEngine":
        if cls._instance is None:
            obj = object.__new__(cls)
            obj._processor = None  # type: ignore[attr-defined]
            obj._model = None  # type: ignore[attr-defined]
            cls._instance = obj
        return cls._instance

    def _ensure_model(self):
        if self._processor is not None and self._model is not None:
            return self._processor, self._model

        try:
            import torch  # type: ignore[import]
            from huggingface_hub import snapshot_download  # type: ignore[import]
            from transformers import AutoProcessor, HunYuanVLForConditionalGeneration  # type: ignore[import]
        except ImportError as e:
            raise ImportError(
                "HunyuanOCR dependencies missing. Install: "
                "pip install torch huggingface_hub "
                "git+https://github.com/huggingface/transformers@82a06db03535c49aa987719ed0746a76093b1ec4"
            ) from e

        print("[*] Initializing HunyuanOCR locally (first use, may download model)...")
        local_model_dir = snapshot_download(repo_id="tencent/HunyuanOCR")
        processor = AutoProcessor.from_pretrained(
            local_model_dir,
            use_fast=False,
            trust_remote_code=True,
        )
        model_kwargs = {
            "attn_implementation": "eager",
            "dtype": torch.bfloat16,
            "trust_remote_code": True,
        }
        try:
            model = HunYuanVLForConditionalGeneration.from_pretrained(
                local_model_dir,
                device_map="auto",
                **model_kwargs,
            )
        except ValueError as e:
            if "requires `accelerate`" not in str(e):
                raise
            model = HunYuanVLForConditionalGeneration.from_pretrained(
                local_model_dir,
                **model_kwargs,
            )
        self._processor = processor
        self._model = model
        print("[+] HunyuanOCR initialized.")
        return processor, model

    def recognize(self, image: Image.Image) -> list[OcrLine]:
        processor, model = self._ensure_model()
        text = self._infer(processor, model, image)
        lines = self._parse_hunyuan_output(text, image.width, image.height)
        lines.sort(key=lambda ln: ln.center_y)
        return lines

    def merge_wechat_sidebar_list_rows(self, lines: list[OcrLine]) -> list[OcrLine]:
        return self.merge_rows(lines)

    def _infer(self, processor, model, image: Image.Image) -> str:
        import torch  # type: ignore[import]

        rgb = image.convert("RGB")
        prompt_text = "检测并识别图片中的文字，将文本坐标格式化输出。"
        messages = [
            {"role": "system", "content": ""},
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": rgb},
                    {"type": "text", "text": prompt_text},
                ],
            },
        ]
        prompt = processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = processor(text=[prompt], images=rgb, padding=True, return_tensors="pt")
        device = next(model.parameters()).device
        inputs = inputs.to(device)
        with torch.no_grad():
            generated_ids = model.generate(
                **inputs,
                max_new_tokens=4096,
                do_sample=False,
            )
        generated_ids_trimmed = [
            out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
        ]
        output_texts = processor.batch_decode(
            generated_ids_trimmed,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )
        return output_texts[0] if output_texts else ""

    def _parse_hunyuan_output(self, raw_text: str, width: int, height: int) -> list[OcrLine]:
        lines = self._parse_json_items(raw_text, width, height)
        if lines:
            return lines
        lines = self._parse_coord_lines(raw_text, width, height)
        if lines:
            return lines
        return self._parse_plain_lines(raw_text, width, height)

    def _parse_json_items(self, raw_text: str, width: int, height: int) -> list[OcrLine]:
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        if start < 0 or end <= start:
            return []
        payload = raw_text[start : end + 1]
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return []
        candidates = data.get("texts") or data.get("results") or data.get("items") or []
        out: list[OcrLine] = []
        for item in candidates:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text", "")).strip()
            bbox = item.get("bbox") or item.get("box") or item.get("coord")
            if not text or not isinstance(bbox, (list, tuple)) or len(bbox) < 4:
                continue
            out.append(self._mk_line(text, bbox[:4], width, height, float(item.get("confidence", 0.9))))
        return [ln for ln in out if ln is not None]

    def _parse_coord_lines(self, raw_text: str, width: int, height: int) -> list[OcrLine]:
        pat = re.compile(
            r"[\[(]\s*(\d+(?:\.\d+)?)\s*[,，]\s*(\d+(?:\.\d+)?)\s*[,，]\s*(\d+(?:\.\d+)?)\s*[,，]\s*(\d+(?:\.\d+)?)\s*[\])]\s*[:：-]?\s*(.+)"
        )
        out: list[OcrLine] = []
        for raw in raw_text.splitlines():
            m = pat.search(raw.strip())
            if not m:
                continue
            text = m.group(5).strip().strip('"').strip("'")
            if not text:
                continue
            box = [m.group(1), m.group(2), m.group(3), m.group(4)]
            line = self._mk_line(text, box, width, height, 0.9)
            if line is not None:
                out.append(line)
        if out:
            return out
        return self._parse_inline_pairs(raw_text, width, height)

    def _parse_inline_pairs(self, raw_text: str, width: int, height: int) -> list[OcrLine]:
        pair_pat = re.compile(
            r"\(\s*(\d+(?:\.\d+)?)\s*[,，]\s*(\d+(?:\.\d+)?)\s*\)\s*,\s*\(\s*(\d+(?:\.\d+)?)\s*[,，]\s*(\d+(?:\.\d+)?)\s*\)"
        )
        matches = list(pair_pat.finditer(raw_text))
        if not matches:
            return []
        out: list[OcrLine] = []
        for i, m in enumerate(matches):
            text_start = 0 if i == 0 else matches[i - 1].end()
            text_end = m.start()
            seg = raw_text[text_start:text_end].strip()
            seg = seg.strip("，,;；|")
            if not seg:
                continue
            box = [m.group(1), m.group(2), m.group(3), m.group(4)]
            line = self._mk_line(seg, box, width, height, 0.9)
            if line is not None:
                out.append(line)
        return out

    def _parse_plain_lines(self, raw_text: str, width: int, height: int) -> list[OcrLine]:
        plain = [ln.strip(" -\t") for ln in raw_text.splitlines() if ln.strip()]
        if not plain:
            return []
        row_h = max(18, height // max(1, len(plain)))
        out: list[OcrLine] = []
        for i, text in enumerate(plain):
            y1 = min(height - 1, i * row_h)
            y2 = min(height, y1 + row_h)
            out.append(OcrLine(text=text, bbox=(0, y1, width, y2), conf=0.5))
        return out

    def _mk_line(
        self,
        text: str,
        box_values: list | tuple,
        width: int,
        height: int,
        conf: float,
    ) -> OcrLine | None:
        arr = np.array(box_values, dtype=float).reshape(-1)
        if arr.size < 4:
            return None
        x1, y1, x2, y2 = [int(v) for v in arr[:4].tolist()]
        x1 = max(0, min(x1, width - 1))
        x2 = max(0, min(x2, width))
        y1 = max(0, min(y1, height - 1))
        y2 = max(0, min(y2, height))
        if x2 <= x1 or y2 <= y1:
            return None
        return OcrLine(text=text, bbox=(x1, y1, x2, y2), conf=float(conf))


_ENGINE: HunyuanOcrEngine | None = None


def get_ocr_engine() -> HunyuanOcrEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = HunyuanOcrEngine()
    return _ENGINE
