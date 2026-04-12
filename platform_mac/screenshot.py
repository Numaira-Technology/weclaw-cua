"""Quartz 窗口截图 & 裁切工具。

功能：
- capture_window(pid) — 按 PID 精确截取单个窗口（Retina 物理像素）
- capture_screen()     — 截取整个主屏幕
- crop_image(img, rect) — 按像素矩形裁切
- crop_region(img, …)   — 按比例裁切
- crop_sidebar / crop_chat_area — 预设比例裁切
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import Quartz  # type: ignore
from PIL import Image


@dataclass
class WindowBounds:
    """窗口在屏幕上的逻辑坐标（含标题栏）。"""
    x: int
    y: int
    width: int
    height: int


# ── 底层 Quartz 工具 ───────────────────────────────────────

def _cg_image_to_pil(cg_image) -> Image.Image:
    """将 CGImage 转为 PIL Image (RGBA)。"""
    width = Quartz.CGImageGetWidth(cg_image)
    height = Quartz.CGImageGetHeight(cg_image)
    bytes_per_row = Quartz.CGImageGetBytesPerRow(cg_image)
    cf_data = Quartz.CGDataProviderCopyData(Quartz.CGImageGetDataProvider(cg_image))
    return Image.frombuffer("RGBA", (width, height), cf_data, "raw", "BGRA", bytes_per_row, 1)


def _find_wechat_cg_window_id(pid: int) -> tuple[int, WindowBounds]:
    """通过 PID 在 Quartz 窗口列表中找到微信主窗口 ID。

    先搜 OnScreenOnly，失败后回退到全部窗口列表（覆盖其他桌面）。
    """
    import time as _time

    for attempt, option in enumerate([
        Quartz.kCGWindowListOptionOnScreenOnly,
        Quartz.kCGWindowListOptionAll,
    ]):
        if attempt > 0:
            _time.sleep(0.5)
        window_list = Quartz.CGWindowListCopyWindowInfo(option, Quartz.kCGNullWindowID)
        best: Optional[tuple[int, WindowBounds]] = None
        for w in window_list:
            if w.get("kCGWindowOwnerPID", 0) != pid:
                continue
            layer = w.get("kCGWindowLayer", -1)
            if layer != 0:
                continue
            bounds = w.get("kCGWindowBounds", {})
            wb = WindowBounds(
                x=int(bounds.get("X", 0)),
                y=int(bounds.get("Y", 0)),
                width=int(bounds.get("Width", 0)),
                height=int(bounds.get("Height", 0)),
            )
            if wb.width < 200 or wb.height < 200:
                continue
            if best is None or (wb.width * wb.height) > (best[1].width * best[1].height):
                best = (int(w["kCGWindowNumber"]), wb)
        if best is not None:
            return best

    raise RuntimeError(
        f"Quartz 窗口列表中未找到 PID={pid} 的可见窗口。\n"
        "请确认微信主窗口已打开且未最小化。"
    )


# ── 截图 API ──────────────────────────────────────────────

def capture_window(pid: int) -> tuple[Image.Image, WindowBounds]:
    """截取指定 PID 的微信主窗口，返回 (PIL Image, 窗口坐标)。

    使用 CGWindowListCreateImage 精确截取单个窗口（不含桌面/其他窗口）。
    返回的图片是物理像素（Retina 下 2x）。
    """
    wid, bounds = _find_wechat_cg_window_id(pid)

    cg_image = Quartz.CGWindowListCreateImage(
        Quartz.CGRectNull,
        Quartz.kCGWindowListOptionIncludingWindow,
        wid,
        Quartz.kCGWindowImageBoundsIgnoreFraming,
    )
    if cg_image is None:
        raise RuntimeError("CGWindowListCreateImage 返回 None，截图失败。")

    return _cg_image_to_pil(cg_image), bounds


def capture_screen() -> Image.Image:
    """截取整个主屏幕（Retina 物理像素）。"""
    cg_image = Quartz.CGWindowListCreateImage(
        Quartz.CGRectInfinite,
        Quartz.kCGWindowListOptionOnScreenOnly,
        Quartz.kCGNullWindowID,
        Quartz.kCGWindowImageDefault,
    )
    if cg_image is None:
        raise RuntimeError("CGWindowListCreateImage 返回 None，全屏截图失败。")
    return _cg_image_to_pil(cg_image)


# ── 裁切 API ──────────────────────────────────────────────

def crop_image(img: Image.Image, rect: tuple[int, int, int, int]) -> Image.Image:
    """按像素矩形裁切：rect = (x, y, width, height)。"""
    x, y, w, h = rect
    return img.crop((x, y, x + w, y + h))


def crop_region(
    img: Image.Image,
    left_ratio: float = 0.0,
    top_ratio: float = 0.0,
    right_ratio: float = 1.0,
    bottom_ratio: float = 1.0,
) -> Image.Image:
    """按比例裁切图片区域。"""
    w, h = img.size
    return img.crop((
        int(w * left_ratio),
        int(h * top_ratio),
        int(w * right_ratio),
        int(h * bottom_ratio),
    ))


# ── 预设区域（使用动态检测的版本见 sidebar_detector.detect_sidebar_region）──

TITLEBAR_BOTTOM = 0.06


def crop_sidebar(img: Image.Image) -> Image.Image:
    """裁切左侧 sidebar（使用动态检测）。"""
    from platform_mac.sidebar_detector import detect_sidebar_region
    return detect_sidebar_region(img).crop_from(img)


def crop_chat_area(img: Image.Image) -> Image.Image:
    """裁切右侧聊天区域（使用动态检测）。"""
    from platform_mac.sidebar_detector import detect_sidebar_region
    w, h = img.size
    sidebar = detect_sidebar_region(img)
    top = int(h * TITLEBAR_BOTTOM)
    return img.crop((sidebar.x2, top, w, h))
