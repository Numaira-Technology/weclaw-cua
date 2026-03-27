#!/usr/bin/env python3
"""Mac 聊天截图 → 长图拼接 → 消息提取 调试脚本。

流程：
  1. 激活微信，扫描 sidebar 未读会话
  2. 点击第一个未读会话（或指定会话）进入
  3. 滚动聊天面板逐帧截图
  4. 拼接为一张长图
  5. (可选) 调用 LLM 提取消息为 JSON

输出到 debug_outputs/capture/
  pass_screenshots/  — 每帧截图
  long_image.png     — 拼接后的长图
  messages.json      — 提取的消息（如果启用 --extract）

用法：
  python scripts/debug_mac_capture_chat.py
  python scripts/debug_mac_capture_chat.py --extract
  python scripts/debug_mac_capture_chat.py --chat "群聊名称"
  python scripts/debug_mac_capture_chat.py --direction down --passes 10
"""

from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image, ImageDraw, ImageFont

from platform_mac.driver import MacDriver
from platform_mac.sidebar_detector import ChatInfo, scan_sidebar_once
from platform_mac.chat_panel_detector import capture_right_panel, get_header_image
from algo_a.click_into_chat import click_chat_row, wait_chat_panel_ready
from algo_a.capture_chat import (
    CaptureSettings,
    capture_scroll_screenshots,
    capture_and_stitch,
)
from algo_a.llm_image_prep import DEFAULT_MAX_SIDE_PIXELS

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "debug_outputs", "capture")


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _try_font(size: int = 18):
    for p in ["/System/Library/Fonts/PingFang.ttc",
              "/System/Library/Fonts/STHeiti Light.ttc",
              "/System/Library/Fonts/Helvetica.ttc"]:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _find_target_chat(driver: MacDriver, target_name: str | None) -> ChatInfo | None:
    """扫描 sidebar 找到目标会话。"""
    img = driver.capture_wechat_window()
    bounds = driver.get_window_bounds()
    from platform_mac.screenshot import WindowBounds
    from platform_mac.sidebar_detector import Rect
    wb = Rect(bounds.x, bounds.y, bounds.width, bounds.height)
    chats = scan_sidebar_once(img, only_unread=False, window_bounds=wb)

    if target_name:
        from platform_mac.chat_panel_detector import titles_match
        for c in chats:
            if titles_match(c.name, target_name):
                return c
        print(f"[!] 未找到名为 '{target_name}' 的会话")
        print(f"    可见会话: {[c.name for c in chats[:10]]}")
        return None

    unread = [c for c in chats if c.badge_type != "none"]
    if unread:
        print(f"[*] 找到 {len(unread)} 个未读会话，使用第一个: {unread[0].name}")
        return unread[0]

    if chats:
        print(f"[*] 无未读会话，使用第一个可见会话: {chats[0].name}")
        return chats[0]

    print("[!] sidebar 中未检测到任何会话")
    return None


def main():
    parser = argparse.ArgumentParser(description="聊天截图 → 长图 → JSON 调试")
    parser.add_argument("--chat", type=str, default=None, help="指定会话名称")
    parser.add_argument("--extract", action="store_true", help="启用 LLM 消息提取")
    parser.add_argument("--model", type=str, default="openrouter/google/gemini-2.5-flash",
                        help="LLM 模型")
    parser.add_argument("--direction", type=str, default="up",
                        choices=["up", "down"], help="滚动方向")
    parser.add_argument("--passes", type=int, default=15, help="最大滚动帧数")
    parser.add_argument("--scroll-clicks", type=int, default=5, help="每帧滚动行数")
    parser.add_argument(
        "--max-side",
        type=int,
        default=DEFAULT_MAX_SIDE_PIXELS,
        help="--extract 时送 LLM 的长边像素上限（0=不缩小）",
    )
    args = parser.parse_args()

    _ensure_dir(OUTPUT_DIR)
    pass_dir = os.path.join(OUTPUT_DIR, "pass_screenshots")
    _ensure_dir(pass_dir)

    print("=" * 60)
    print("  Mac 聊天截图 → 长图拼接 调试脚本")
    print("=" * 60)

    driver = MacDriver()
    driver.ensure_permissions()
    driver.find_wechat_window()
    driver.activate_wechat()
    time.sleep(0.5)

    # 找到目标会话
    target = _find_target_chat(driver, args.chat)
    if target is None:
        sys.exit(1)

    print(f"\n[1] 目标会话: {target.name}")
    print(f"    badge={target.badge_type}, unread={target.unread_count}")

    # 点击进入会话
    print(f"\n[2] 点击进入会话...")
    cx, cy = click_chat_row(driver, target)
    print(f"    click point: ({cx}, {cy})")
    time.sleep(0.5)

    result = wait_chat_panel_ready(driver, target.name, timeout=5.0)
    if result.ready:
        print(f"    ✓ 右侧面板已切换到: {result.detected_title}")
    else:
        print(f"    ✗ 右侧面板未确认: reason={result.reason}, title={result.detected_title}")
        print("    继续截图...")

    # 保存进入后的截图
    window_img = driver.capture_wechat_window()
    window_img.save(os.path.join(OUTPUT_DIR, "entered_chat.png"))
    panel = capture_right_panel(window_img)
    panel.save(os.path.join(OUTPUT_DIR, "right_panel.png"))
    header = get_header_image(window_img)
    header.save(os.path.join(OUTPUT_DIR, "header.png"))

    # 滚动截图 + 拼接
    settings = CaptureSettings(
        max_passes=args.passes,
        scroll_clicks=args.scroll_clicks,
        scroll_direction=args.direction,
        min_new_content_px=60,
        min_overlap_score=0.55,
        min_seam_corr=0.35,
    )

    long_image_path = os.path.join(OUTPUT_DIR, "long_image.png")
    print(f"\n[3] 开始滚动截图 (direction={args.direction}, max_passes={args.passes})...")

    result = capture_and_stitch(
        driver=driver,
        output_path=long_image_path,
        capture_dir=pass_dir,
        chat_name=target.name or "chat",
        settings=settings,
    )

    long_img: Image.Image = result["long_image"]
    pass_count = result["pass_count"]
    overlaps = result["pair_overlaps"]
    scores = result["match_scores"]

    print(f"\n[4] 拼接完成:")
    print(f"    帧数: {pass_count}")
    print(f"    长图尺寸: {long_img.size[0]} x {long_img.size[1]} px")
    if overlaps:
        print(f"    重叠高度: {overlaps}")
        print(f"    匹配得分: {[f'{s:.3f}' for s in scores]}")
    print(f"    保存到: {long_image_path}")

    # 可选：LLM 消息提取
    if args.extract:
        print(f"\n[5] 调用 LLM 提取消息 (model={args.model})...")
        try:
            from algo_a.extract_messages import extract_and_save
            json_path = os.path.join(OUTPUT_DIR, "messages.json")
            extract_result = extract_and_save(
                image=long_img,
                output_path=json_path,
                model=args.model,
                max_side_pixels=args.max_side,
            )
            msgs = extract_result["messages"]
            print(f"    ✓ 提取到 {len(msgs)} 条消息")
            print(f"    confidence: {extract_result['extraction_confidence']}")
            print(f"    boundary:   {extract_result['boundary_stability']}")
            for i, m in enumerate(msgs[:5]):
                content_preview = m["content"][:40] + ("..." if len(m["content"]) > 40 else "")
                print(f"    [{i}] {m['sender']}: {content_preview}")
            if len(msgs) > 5:
                print(f"    ... 还有 {len(msgs) - 5} 条消息")
        except ImportError:
            print("    ✗ litellm 未安装，跳过消息提取")
            print("    安装: pip install litellm")
        except Exception as e:
            print(f"    ✗ 消息提取失败: {e}")
    else:
        print(f"\n[提示] 添加 --extract 参数可启用 LLM 消息提取")

    print(f"\n{'=' * 60}")
    print(f"  调试输出目录: {os.path.abspath(OUTPUT_DIR)}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
