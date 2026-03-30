#!/usr/bin/env python3
"""Mac Step 4：根据 Step 3 产出的长图提取消息（不另截图、不裁 viewport）。

默认长图（未传 --long-image 时）：
  - 若提供 --chat：优先 debug_outputs/batch_multichat/{会话安全名}/long_image.png（与 debug_mac_multiple_chats 一致）
  - 否则：debug_outputs/capture/long_image.png（与 debug_mac_capture_chat.py 一致）

输出到 debug_outputs/read_visible/
  long_image.png   — 从输入复制一份，便于对照
  messages.json    — 提取的消息

用法：
  # 先跑 Step 3 生成长图，再：
  export OPENROUTER_API_KEY=...
  python3 scripts/debug_mac_read_visible_messages.py --chat "会话名"

  python3 scripts/debug_mac_read_visible_messages.py --long-image /path/to/long_image.png --chat "会话名"

  # 若需先激活微信并点进会话（仍只从长图读消息）：
  python3 scripts/debug_mac_read_visible_messages.py --with-wechat --chat "会话名"
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from platform_mac.driver import MacDriver
from platform_mac.sidebar_detector import ChatInfo, Rect, scan_sidebar_once
from platform_mac.chat_panel_detector import titles_match
from algo_a.click_into_chat import click_chat_row, wait_chat_panel_ready
from algo_a.read_visible_messages import messages_to_dicts
from algo_a.extract_messages import DEFAULT_EXTRACT_MODEL
from algo_a.llm_image_prep import DEFAULT_MAX_SIDE_PIXELS
from algo_a.read_long_image_messages import read_messages_from_long_image_file

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
OUTPUT_DIR = os.path.join(REPO_ROOT, "debug_outputs", "read_visible")
CAPTURE_LONG_IMAGE = os.path.join(REPO_ROOT, "debug_outputs", "capture", "long_image.png")
BATCH_MULTICHAT_ROOT = os.path.join(REPO_ROOT, "debug_outputs", "batch_multichat")


def _safe_chat_dir(chat: str) -> str:
    return chat.replace("/", "_").replace("\\", "_").replace(":", "_")


def _resolve_long_image_path(long_image_arg: str | None, chat: str | None) -> tuple[str, str]:
    """返回 (绝对路径, 来源说明)。long_image_arg 非空时始终使用该路径。"""
    if long_image_arg:
        return os.path.abspath(long_image_arg), f"--long-image ({long_image_arg})"
    if chat and chat.strip():
        safe = _safe_chat_dir(chat.strip())
        batch_p = os.path.join(BATCH_MULTICHAT_ROOT, safe, "long_image.png")
        if os.path.isfile(batch_p):
            return os.path.abspath(batch_p), f"batch_multichat/{safe}/long_image.png"
    cap = os.path.abspath(CAPTURE_LONG_IMAGE)
    if os.path.isfile(cap):
        return cap, "debug_outputs/capture/long_image.png"
    if chat and chat.strip():
        batch_p = os.path.join(BATCH_MULTICHAT_ROOT, _safe_chat_dir(chat.strip()), "long_image.png")
        return os.path.abspath(batch_p), f"batch_multichat/{_safe_chat_dir(chat.strip())}/long_image.png (不存在)"
    return cap, "debug_outputs/capture/long_image.png (不存在)"


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _find_target(driver: MacDriver, target_name: str | None) -> ChatInfo | None:
    img, wb = driver.capture_wechat_window_with_bounds()
    win_rect = Rect(wb.x, wb.y, wb.width, wb.height)
    chats = scan_sidebar_once(img, only_unread=False, window_bounds=win_rect)

    if target_name:
        for c in chats:
            if titles_match(c.name, target_name):
                return c
        print(f"[!] 未找到 '{target_name}'")
        print(f"    可见: {[c.name for c in chats[:10]]}")
        return None

    unread = [c for c in chats if c.badge_type != "none"]
    if unread:
        print(f"[*] 找到 {len(unread)} 个未读，使用: {unread[0].name}")
        return unread[0]
    if chats:
        print(f"[*] 无未读，使用第一个可见: {chats[0].name}")
        return chats[0]
    print("[!] sidebar 无会话")
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Step 4：从长图提取消息")
    parser.add_argument(
        "--long-image",
        type=str,
        default=None,
        help="长图路径；省略时：有 --chat 则先试 batch_multichat/{chat}/long_image.png，再试 capture/long_image.png",
    )
    parser.add_argument("--chat", type=str, default=None, help="会话名（注入 LLM）")
    parser.add_argument("--model", type=str, default=DEFAULT_EXTRACT_MODEL)
    parser.add_argument(
        "--max-side",
        type=int,
        default=DEFAULT_MAX_SIDE_PIXELS,
        help="送 LLM 前长边最大像素（默认与 algo 一致；0=不缩小）",
    )
    parser.add_argument(
        "--chunks",
        type=int,
        default=2,
        help="chunk-max-height=0 时固定竖切条数（1～10）；否则由高度自动算条数",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=float,
        default=0.08,
        help="分段相邻重叠比例（仅多段），减轻截断气泡",
    )
    parser.add_argument(
        "--chunk-max-height",
        type=int,
        default=2400,
        help="单条最大高度(px)自动算条数，上限 --chunk-max-count；0=用 --chunks 固定",
    )
    parser.add_argument(
        "--chunk-max-count",
        type=int,
        default=10,
        help="自动分段最多条数",
    )
    parser.add_argument(
        "--with-wechat",
        action="store_true",
        help="激活微信并可选进入会话；消息仍只从 --long-image 读取",
    )
    parser.add_argument(
        "--skip-click",
        action="store_true",
        help="与 --with-wechat 合用：不点 sidebar，需 --chat",
    )
    args = parser.parse_args()
    if not (1 <= args.chunks <= 10):
        print("[!] --chunks 须在 1～10")
        sys.exit(1)

    long_path, long_src = _resolve_long_image_path(args.long_image, args.chat)
    if not os.path.isfile(long_path):
        print(f"[!] 找不到长图: {long_path}")
        print(f"    解析来源: {long_src}")
        print("    可指定: --long-image /path/to/long_image.png")
        print("    或先跑: python3 scripts/debug_mac_multiple_chats.py")
        print("         或: python3 scripts/debug_mac_capture_chat.py")
        sys.exit(1)

    _ensure_dir(OUTPUT_DIR)

    print("=" * 60)
    print("  Step 4: 根据长图提取消息")
    print("=" * 60)

    chat_name = args.chat or ""

    if args.with_wechat:
        driver = MacDriver()
        driver.ensure_permissions()
        driver.find_wechat_window()
        driver.activate_wechat()
        time.sleep(0.5)

        if args.skip_click:
            if not chat_name:
                from platform_mac.chat_panel_detector import extract_chat_header_title
                window_img = driver.capture_wechat_window()
                chat_name = extract_chat_header_title(window_img) or "unknown"
                print(f"[*] 自动检测标题: {chat_name}")
            print(f"[1] 跳过点击，会话: {chat_name}")
        else:
            target = _find_target(driver, args.chat)
            if target is None:
                sys.exit(1)
            chat_name = target.name
            print(f"\n[1] 目标: {chat_name} (badge={target.badge_type})")
            print("[2] 点击进入...")
            click_chat_row(driver, target)
            time.sleep(0.5)
            result = wait_chat_panel_ready(
                driver, chat_name, timeout=5.0, anchor_row_rect=target.row_rect,
            )
            if result.ready:
                print(f"    OK — 标题: {result.detected_title}")
            else:
                print(f"    WARN — {result.reason}: {result.detected_title}")

    if not chat_name:
        print("[!] 请用 --chat 指定会话名（与 Step 3 一致即可）。")
        sys.exit(1)

    print(f"\n[读取] 长图: {long_path}")
    print(f"        来源: {long_src}")
    print(
        f"[LLM]  model={args.model}  max_side={args.max_side}px  "
        f"chunk_max_height={args.chunk_max_height}  chunks_fixed={args.chunks}",
    )
    if args.chunk_max_height <= 0 and args.chunks == 1:
        print(
            "    （接下来会先编码整图，再请求云端；长图可能要 1～5 分钟才有结果，"
            "终端会出现 [read_visible] 进度行）",
            flush=True,
        )
    elif args.chunk_max_height <= 0:
        print(
            f"    （固定拆成 {args.chunks} 段；每段会打印 [read_visible] 进度）",
            flush=True,
        )
    else:
        print(
            "    （按高度自动分段，每段会打印 [read_visible] 进度）",
            flush=True,
        )

    try:
        messages, _, meta = read_messages_from_long_image_file(
            long_path,
            chat_name,
            model=args.model,
            max_side_pixels=args.max_side,
            chunk_count=args.chunks,
            chunk_overlap_ratio=args.chunk_overlap,
            chunk_max_strip_height_px=args.chunk_max_height,
            chunk_max_count=args.chunk_max_count,
        )
    except Exception as e:
        print(f"    提取失败: {e}")
        sys.exit(1)

    out_long = os.path.join(OUTPUT_DIR, "long_image.png")
    shutil.copy2(long_path, out_long)

    print(f"    提取到 {len(messages)} 条消息")
    ec = meta.get("effective_chunk_count", meta.get("chunk_count"))
    if ec is not None:
        print(f"    分段数 effective_chunk_count={ec}", flush=True)

    print(f"\n{'─' * 60}")
    print(f"  消息列表 — {chat_name}")
    print(f"{'─' * 60}")
    for i, m in enumerate(messages):
        time_str = m.time or ""
        type_tag = f"[{m.type}]" if m.type != "text" else ""
        content_preview = m.content[:60] + ("..." if len(m.content) > 60 else "")
        print(f"  {i:2d}. {type_tag}{m.sender}: {content_preview}  {time_str}")

    json_path = os.path.join(OUTPUT_DIR, "messages.json")
    save_data = {
        "chat_name": chat_name,
        "message_count": len(messages),
        "model": meta.get("model", ""),
        "long_image_source": meta.get("long_image_path", ""),
        "long_image_size": list(meta.get("long_image_size", ())),
        "chunked": meta.get("chunked"),
        "chunk_count": meta.get("chunk_count"),
        "effective_chunk_count": meta.get("effective_chunk_count"),
        "chunk_max_strip_height_px": meta.get("chunk_max_strip_height_px"),
        "chunk_max_count": meta.get("chunk_max_count"),
        "long_image_height_px": meta.get("long_image_height_px"),
        "chunk_overlap_ratio": meta.get("chunk_overlap_ratio"),
        "chunks": meta.get("chunks"),
        "source_image_size": meta.get("source_image_size"),
        "llm_image_size": meta.get("llm_image_size"),
        "max_side_pixels": meta.get("max_side_pixels"),
        "messages": messages_to_dicts(messages),
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)

    print(f"\n已保存:")
    print(f"    {os.path.abspath(out_long)}")
    print(f"    {os.path.abspath(json_path)}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
