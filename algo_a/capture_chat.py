"""滚动翻拍聊天面板 → 截图 → 拼接长图。

流程（移植自 wechat-admin-bot-main/workflow/chat_whole_pic.py）：
  1. 将鼠标移至聊天面板中心并 click 获取焦点
  2. 循环：scroll → 截图 → 裁切聊天区 → 估算重叠 → 判断停止
  3. 将所有截图拼接为一张长图

关键设计：
  - 支持向上滚动（查看历史）和向下滚动
  - 向上滚动时，新旧帧的重叠边界是反的：
    curr 的 BOTTOM 与 prev 的 TOP 重叠
    因此需要交换 overlap 估算参数，最后反转帧序再拼接

适配 weclaw-main：
  - 使用 MacDriver（Quartz 截图 + CGEvent 滚动）
  - 使用 detect_sidebar_region 动态裁切聊天内容区域
  - 全程同步（无 asyncio）

输入：已进入目标会话的 MacDriver
输出：拼接后的长图 + 元数据
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from PIL import Image

from platform_mac.sidebar_detector import Rect, detect_sidebar_region, TITLEBAR_HEIGHT_RATIO
from platform_mac.image_stitcher import estimate_pair_overlap, stitch_screenshots


# ── 配置 ──────────────────────────────────────────────────

@dataclass
class CaptureSettings:
    """滚动截图 + 拼接的配置参数。

    min_pass_index_for_stop：日志里 pass N 的 N 达到该值后才允许用「新内容少 + 边缘/滚动条静止」
    判停；否则首轮滚动易被误判为已到顶，导致只滚一次就结束。
    """
    max_passes: int = 15
    scroll_clicks: int = 5
    scroll_bursts: int = 3
    scroll_direction: str = "up"
    min_new_content_px: int = 60
    min_overlap_score: float = 0.55
    min_seam_corr: float = 0.35
    scroll_interval: float = 0.40
    header_skip_ratio: float = 0.07
    footer_skip_ratio: float = 0.11
    min_pass_index_for_stop: int = 3

DEFAULT_SETTINGS = CaptureSettings()


# ── 聊天区域裁切 ──────────────────────────────────────────

def _crop_chat_content(window_img: Image.Image,
                       header_skip: float = 0.07,
                       footer_skip: float = 0.11,
                       sidebar_x2: int | None = None) -> Image.Image:
    """从窗口截图裁切出纯聊天消息内容区域。

    跳过顶部标题栏和底部输入框/工具栏，只保留消息气泡区域。
    sidebar_x2: 如果提供，直接用此值作为 sidebar 右边界（保证多帧一致）。
    """
    w, h = window_img.size
    left = sidebar_x2 if sidebar_x2 is not None else detect_sidebar_region(window_img).x2
    top = int(h * (TITLEBAR_HEIGHT_RATIO + header_skip))
    bottom = int(h * (1.0 - footer_skip))
    return window_img.crop((left, top, w, bottom))


# ── 停止条件判断 ──────────────────────────────────────────

def _crops_identical(prev: Image.Image, curr: Image.Image, threshold: float = 1.5) -> bool:
    """两帧裁切图是否几乎完全相同（滚到头了）。"""
    p = np.array(prev.convert("L"))
    c = np.array(curr.convert("L"))
    h = min(p.shape[0], c.shape[0])
    w = min(p.shape[1], c.shape[1])
    if h < 10 or w < 10:
        return False
    diff = np.abs(p[:h, :w].astype(np.int16) - c[:h, :w].astype(np.int16))
    return float(diff.max()) <= threshold


def _scrollbar_static(prev_full: Image.Image, curr_full: Image.Image) -> bool:
    """整窗截图：右侧窄条（滚动条区域）两帧是否几乎不变。

    对应 wechat-admin-bot `workflow/chat_whole_pic._scrollbar_static` /
    `modules/whole_pic_generator` 搭配使用的停止信号，与底部条带二选一即可判停。
    """
    p = np.array(prev_full.convert("L"))
    c = np.array(curr_full.convert("L"))
    h = min(p.shape[0], c.shape[0])
    w = min(p.shape[1], c.shape[1])
    if h < 20 or w < 20:
        return False
    p, c = p[:h, :w], c[:h, :w]
    strip_w = max(6, int(w * 0.012))
    x0 = w - strip_w
    y0 = int(h * 0.06)
    y1 = int(h * 0.94)
    prev_roi = p[y0:y1, x0:w]
    curr_roi = c[y0:y1, x0:w]
    if prev_roi.shape != curr_roi.shape or prev_roi.size == 0:
        return False
    diff = np.abs(prev_roi.astype(np.int16) - curr_roi.astype(np.int16))
    changed = float(np.count_nonzero(diff > 10)) / float(diff.size)
    mean_diff = float(diff.mean())
    return changed < 0.01 and mean_diff < 2.0


def _edge_strip_static(prev: Image.Image, curr: Image.Image,
                       scrolling_up: bool) -> bool:
    """滚动方向上的边缘窄条是否静止（判断已滚到头）。

    向上滚动时检查顶部窄条，向下滚动时检查底部窄条。
    """
    p = np.array(prev.convert("L"))
    c = np.array(curr.convert("L"))
    h = min(p.shape[0], c.shape[0])
    w = min(p.shape[1], c.shape[1])
    if h < 20 or w < 20:
        return False
    p, c = p[:h, :w], c[:h, :w]
    strip_h = min(150, max(80, int(h * 0.14)))
    if scrolling_up:
        prev_strip = p[:strip_h, :]
        curr_strip = c[:strip_h, :]
    else:
        prev_strip = p[-strip_h:, :]
        curr_strip = c[-strip_h:, :]
    diff = np.abs(prev_strip.astype(np.int16) - curr_strip.astype(np.int16))
    changed = float(np.count_nonzero(diff > 10)) / float(diff.size)
    return changed < 0.025 and float(diff.mean()) < 3.0


def _pil_to_bgr(img: Image.Image) -> np.ndarray:
    # 与 image_stitcher 共用延迟加载，失败时提示一致
    from platform_mac.image_stitcher import _cv2

    cv2 = _cv2()
    return cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)


# ── 核心流程 ──────────────────────────────────────────────

def _frames_near_duplicate(prev: Image.Image, curr: Image.Image,
                           threshold: float = 0.02) -> bool:
    """两帧是否几乎相同（滚动无效或只有动画差异）。

    用中间 60% 区域的变化像素比例判断。
    """
    p = np.array(prev.convert("L"))
    c = np.array(curr.convert("L"))
    h = min(p.shape[0], c.shape[0])
    w = min(p.shape[1], c.shape[1])
    if h < 20 or w < 20:
        return False
    y0, y1 = int(h * 0.2), int(h * 0.8)
    diff = np.abs(p[y0:y1, :w].astype(np.int16) - c[y0:y1, :w].astype(np.int16))
    changed = float(np.count_nonzero(diff > 8)) / float(diff.size)
    return changed < threshold


def capture_scroll_screenshots(
    driver,
    capture_dir: Optional[str] = None,
    chat_name: str = "chat",
    settings: Optional[CaptureSettings] = None,
) -> List[Image.Image]:
    """滚动聊天面板并逐帧截图，返回裁切后的聊天内容图列表。

    返回的列表已按拼接顺序排列（最旧在前，最新在后）。
    sidebar 只检测一次，保证所有帧裁切宽度一致。
    """
    cfg = settings or DEFAULT_SETTINGS
    scrolling_up = cfg.scroll_direction == "up"

    if capture_dir:
        os.makedirs(capture_dir, exist_ok=True)

    # 对齐 chat_whole_pic：先点击聊天区中心聚焦，再截图
    driver.focus_chat_panel()
    time.sleep(0.25)
    window_img = driver.capture_wechat_window()
    sidebar_x2 = detect_sidebar_region(window_img).x2

    screenshots: list[Image.Image] = []
    chat_crop = _crop_chat_content(window_img, cfg.header_skip_ratio,
                                   cfg.footer_skip_ratio, sidebar_x2=sidebar_x2)
    screenshots.append(chat_crop)
    if capture_dir:
        chat_crop.save(os.path.join(capture_dir, f"{chat_name}_pass0.png"))

    prev_crop = chat_crop
    prev_window_img = window_img
    overlap_hint: Optional[int] = None
    stop_streak = 0
    dup_streak = 0

    for idx in range(1, cfg.max_passes + 1):
        driver.move_mouse_to_chat_panel()
        time.sleep(0.06)
        delta = cfg.scroll_clicks if scrolling_up else -cfg.scroll_clicks
        driver.scroll_chat_panel(delta=delta, bursts=cfg.scroll_bursts)
        time.sleep(cfg.scroll_interval)

        window_img = driver.capture_wechat_window()
        chat_crop = _crop_chat_content(window_img, cfg.header_skip_ratio,
                                       cfg.footer_skip_ratio, sidebar_x2=sidebar_x2)

        if capture_dir:
            chat_crop.save(os.path.join(capture_dir, f"{chat_name}_pass{idx}.png"))

        if _crops_identical(prev_crop, chat_crop) or _frames_near_duplicate(prev_crop, chat_crop):
            dup_streak += 1
            print(f"[capture_chat] pass {idx}: near-duplicate (streak={dup_streak}) — skip")
            if dup_streak >= 2:
                print(f"[capture_chat] stop: scroll had no effect")
                break
            continue
        dup_streak = 0

        prev_bgr = _pil_to_bgr(prev_crop)
        curr_bgr = _pil_to_bgr(chat_crop)

        if scrolling_up:
            metrics = estimate_pair_overlap(curr_bgr, prev_bgr, overlap_hint=overlap_hint)
        else:
            metrics = estimate_pair_overlap(prev_bgr, curr_bgr, overlap_hint=overlap_hint)

        new_h = int(metrics["new_h"])
        score = float(metrics["score"])
        seam_corr = float(metrics["seam_corr"])
        overlap_ratio = int(metrics["overlap_h"]) / max(1, min(prev_bgr.shape[0], curr_bgr.shape[0]))
        edge_static = _edge_strip_static(prev_crop, chat_crop, scrolling_up)
        bar_static = _scrollbar_static(prev_window_img, window_img)
        similarity_ok = score >= cfg.min_overlap_score or seam_corr >= cfg.min_seam_corr
        # 对齐 chat_whole_pic：new_h 小 + 匹配可信 + (底/顶边条静止 或 滚动条区域静止)
        should_stop = (
            new_h < cfg.min_new_content_px
            and similarity_ok
            and (edge_static or bar_static)
        )

        print(
            f"[capture_chat] pass {idx}: "
            f"new_h={new_h}, score={score:.3f}, seam={seam_corr:.3f}, "
            f"overlap={overlap_ratio:.1%}, edge_static={edge_static}, "
            f"scrollbar_static={bar_static}, stop={should_stop}"
        )

        if should_stop and idx >= cfg.min_pass_index_for_stop:
            stop_streak += 1
        else:
            stop_streak = 0

        if stop_streak >= 1:
            print(f"[capture_chat] stop triggered at pass {idx}")
            break

        screenshots.append(chat_crop)
        overlap_hint = int(metrics["overlap_h"])
        prev_crop = chat_crop
        prev_window_img = window_img

    if scrolling_up:
        screenshots.reverse()

    return screenshots


def capture_and_stitch(
    driver,
    output_path: Optional[str] = None,
    capture_dir: Optional[str] = None,
    chat_name: str = "chat",
    settings: Optional[CaptureSettings] = None,
) -> Dict[str, object]:
    """完整流程：滚动截图 → 拼接长图。

    返回 dict:
      long_image     — 拼接后的 PIL Image
      screenshots    — 各帧截图 (PIL Image)，拼接顺序（旧→新）
      pair_overlaps  — 每对重叠高度
      match_scores   — 匹配得分
      output_path    — 保存路径（如果提供）
      pass_count     — 总帧数
    """
    screenshots = capture_scroll_screenshots(
        driver=driver,
        capture_dir=capture_dir,
        chat_name=chat_name,
        settings=settings,
    )

    result = stitch_screenshots(screenshots, output_path=output_path)
    result["screenshots"] = screenshots
    result["pass_count"] = len(screenshots)
    return result
