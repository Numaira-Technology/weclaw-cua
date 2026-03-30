"""macOS Vision 框架 OCR：无需外部依赖，支持中英文混合识别。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from PIL import Image


@dataclass
class OCRResult:
    """单条 OCR 识别结果。"""
    text: str
    confidence: float
    x: float          # 归一化 bbox 左上角 x (0~1)
    y: float          # 归一化 bbox 左上角 y (0~1)
    width: float      # 归一化宽度
    height: float     # 归一化高度
    pixel_y: int = 0  # 在原图中的像素 y（用于排序）


def prepare_image_for_vision_ocr(img: Image.Image, min_side: int = 56) -> Image.Image:
    """转为 RGB，并在最短边过小时整体放大，减少 Vision 对小图返回空结果的情况。"""
    out = img.convert("RGB")
    w, h = out.size
    m = min(w, h)
    assert m > 0
    if m < min_side:
        scale = max(2, (min_side + m - 1) // m)
        out = out.resize((w * scale, h * scale), Image.Resampling.LANCZOS)
    return out


def ocr_image(
    img: Image.Image,
    languages: list[str] | None = None,
    min_confidence: float = 0.3,
) -> List[OCRResult]:
    """对 PIL Image 执行 OCR，返回按 y 坐标排序的识别结果列表。

    使用 macOS Vision 框架 VNRecognizeTextRequest，无需外部 OCR 引擎。
    """
    import objc  # type: ignore
    import Vision  # type: ignore
    from Foundation import NSData  # type: ignore
    from Quartz import (  # type: ignore
        CGImageSourceCreateWithData,
        CGImageSourceCreateImageAtIndex,
    )

    if languages is None:
        languages = ["zh-Hans", "zh-Hant", "en-US"]

    # PIL Image → CGImage
    from io import BytesIO
    buf = BytesIO()
    img.save(buf, format="PNG")
    png_data = buf.getvalue()

    ns_data = NSData.dataWithBytes_length_(png_data, len(png_data))
    img_source = CGImageSourceCreateWithData(ns_data, None)
    if img_source is None:
        return []
    cg_image = CGImageSourceCreateImageAtIndex(img_source, 0, None)
    if cg_image is None:
        return []

    # Vision OCR
    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg_image, {})
    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLanguages_(languages)
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setUsesLanguageCorrection_(True)

    success = handler.performRequests_error_([request], None)
    if not success[0]:
        return []

    results: List[OCRResult] = []
    img_h = img.height

    for obs in request.results():
        top_candidate = obs.topCandidates_(1)
        if not top_candidate:
            continue
        candidate = top_candidate[0]
        text = str(candidate.string())
        conf = float(candidate.confidence())

        if conf < min_confidence:
            continue

        # Vision bbox: 左下角为原点, 归一化坐标
        bbox = obs.boundingBox()
        bx = bbox.origin.x
        by = bbox.origin.y
        bw = bbox.size.width
        bh = bbox.size.height

        # 转换为左上角原点
        top_y = 1.0 - by - bh

        results.append(OCRResult(
            text=text,
            confidence=conf,
            x=bx,
            y=top_y,
            width=bw,
            height=bh,
            pixel_y=int(top_y * img_h),
        ))

    results.sort(key=lambda r: (r.pixel_y, r.x))
    return results


def format_ocr_results(results: List[OCRResult], label: str = "") -> str:
    """把 OCR 结果格式化为可读文本。"""
    if not results:
        return f"[{label}] 无 OCR 结果"
    lines = [f"[{label}] OCR 识别到 {len(results)} 条文本:"]
    for r in results:
        conf_pct = f"{r.confidence * 100:.0f}%"
        pos = f"y={r.pixel_y:4d} x={r.x:.2f}"
        lines.append(f"  {pos}  {conf_pct}  {r.text!r}")
    return "\n".join(lines)
