#!/usr/bin/env python3
"""Mac sidebar 未读扫描 — 可视化调试脚本。

默认只做截图 + 侧栏检测 + 列表，不点击会话。与批量 pipeline 相同的点击/等标题逻辑见：
  --click-first  （调用 algo_a.click_into_chat.click_into_chat）

输出到 debug_outputs/ ：
  window_full.png       — 原始窗口截图
  sidebar_crop.png      — sidebar 裁切
  sidebar_annotated.png — 标注了 row/badge_region/name_region/badge_box 的可视化图
  header_after_click.png — 仅 --click-first：点击后主标题带裁切
  终端输出              — 每行 ChatInfo 详情

用法：
  python3 scripts/debug_mac_sidebar_unread.py
  python3 scripts/debug_mac_sidebar_unread.py --click-first
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import load_config
from PIL import Image, ImageDraw, ImageFont

from platform_mac.driver import MacDriver
from platform_mac.sidebar_detector import (
    ChatInfo,
    Rect,
    compute_row_subregions,
    detect_sidebar_region,
    detect_session_rows,
    detect_unread_badge,
    extract_chat_name,
    scan_sidebar_once,
)
from algo_a.click_into_chat import click_into_chat
from algo_a.list_unread_chats import filter_chats_by_groups_to_monitor, list_unread_chats
from platform_mac.chat_panel_detector import (
    extract_chat_header_title,
    get_header_image,
    list_header_ocr_lines,
)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "debug_outputs")


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _try_load_font(size: int = 16):
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for p in candidates:
        if os.path.isfile(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _draw_rect(draw: ImageDraw.ImageDraw, rect: Rect,
               color: str, width: int = 2, label: str = ""):
    draw.rectangle([rect.x, rect.y, rect.x2, rect.y2], outline=color, width=width)
    if label:
        font = _try_load_font(14)
        draw.text((rect.x + 4, rect.y + 2), label, fill=color, font=font)


def annotate_sidebar(sidebar_img: Image.Image) -> tuple[Image.Image, list[dict]]:
    """在 sidebar 图上标注：
      - row_rect（绿/蓝框）
      - badge_region（黄框）
      - name_region（青框）
      - 实际检测到的 badge_box（红框）
    """
    annotated = sidebar_img.copy()
    draw = ImageDraw.Draw(annotated)
    font = _try_load_font(18)

    rows = detect_session_rows(sidebar_img)
    row_details: list[dict] = []

    for i, row_rect in enumerate(rows):
        row_img = row_rect.crop_from(sidebar_img)
        w, h = row_img.size
        regions = compute_row_subregions(w, h)

        # ── row-local 检测 ──
        badge = detect_unread_badge(row_img)
        name = extract_chat_name(row_img)

        # ── 画 row 边界 ──
        row_color = "lime" if badge["has_unread"] else "#4488ff"
        draw.rectangle(
            [row_rect.x, row_rect.y, row_rect.x2, row_rect.y2],
            outline=row_color, width=2,
        )

        # ── 画 badge sub-region（黄框）──
        br = regions.badge
        abs_badge_region = Rect(
            row_rect.x + br.x, row_rect.y + br.y, br.width, br.height
        )
        draw.rectangle(
            [abs_badge_region.x, abs_badge_region.y,
             abs_badge_region.x2, abs_badge_region.y2],
            outline="#FFAA00", width=1,
        )

        # ── 画 name sub-region（青框）──
        nr = regions.name
        abs_name_region = Rect(
            row_rect.x + nr.x, row_rect.y + nr.y, nr.width, nr.height
        )
        draw.rectangle(
            [abs_name_region.x, abs_name_region.y,
             abs_name_region.x2, abs_name_region.y2],
            outline="cyan", width=1,
        )

        # ── 行标签 ──
        label_parts = [f"#{i}"]
        if name:
            label_parts.append(name[:20])
        if badge["has_unread"]:
            if badge["badge_type"] == "count":
                label_parts.append(f"[{badge['unread_count']}]")
            else:
                label_parts.append("[dot]")

        label = " ".join(label_parts)
        draw.text((row_rect.x + 6, row_rect.y + 4), label, fill=row_color, font=font)

        # ── 画实际检测到的 badge box（红框）──
        if badge["badge_rect"] is not None:
            bbr = badge["badge_rect"]
            abs_badge_box = Rect(
                row_rect.x + bbr.x, row_rect.y + bbr.y, bbr.width, bbr.height
            )
            draw.rectangle(
                [abs_badge_box.x, abs_badge_box.y,
                 abs_badge_box.x2, abs_badge_box.y2],
                outline="red", width=2,
            )

        row_details.append({
            "index": i,
            "name": name,
            "badge": badge,
            "rect": row_rect,
            "regions": regions,
        })

    return annotated, row_details


def main():
    parser = argparse.ArgumentParser(description="Sidebar 未读扫描调试（默认不点击）")
    parser.add_argument(
        "--click-first",
        action="store_true",
        help="对 groups_to_monitor 过滤后的第一个未读会话执行 click_into_chat（与批量脚本一致）",
    )
    parser.add_argument(
        "--click-timeout",
        type=float,
        default=12.0,
        help="--click-first 时 wait_chat_panel_ready 超时秒数（默认 12）",
    )
    args = parser.parse_args()

    _ensure_dir(OUTPUT_DIR)
    repo_root = Path(__file__).resolve().parent.parent
    cfg = load_config(str(repo_root / "config" / "config.json"))

    print("=" * 60)
    print("  WeChat Mac Sidebar Unread Scanner — Debug")
    print("=" * 60)
    print(f"  config: wechat_app_name={cfg.wechat_app_name!r}  groups_to_monitor={cfg.groups_to_monitor!r}")

    driver = MacDriver()

    print("\n[1] 检查权限...")
    driver.ensure_permissions()
    print("    ✓ Accessibility 已授权")

    print("[2] 激活微信...")
    driver.find_wechat_window(cfg.wechat_app_name)
    driver.activate_wechat()
    print(f"    ✓ WeChat PID={driver._window.pid}")

    print("    回滚 sidebar 到顶部...")
    driver.scroll_sidebar_to_top()
    time.sleep(0.5)

    print("[3] 截取窗口...")
    window_img = driver.capture_wechat_window()
    full_path = os.path.join(OUTPUT_DIR, "window_full.png")
    window_img.save(full_path)
    print(f"    ✓ {window_img.size[0]}×{window_img.size[1]}  →  {full_path}")

    print("[4] 裁切 sidebar...")
    sidebar_rect = detect_sidebar_region(window_img)
    sidebar_img = sidebar_rect.crop_from(window_img)
    sidebar_path = os.path.join(OUTPUT_DIR, "sidebar_crop.png")
    sidebar_img.save(sidebar_path)
    print(f"    ✓ sidebar {sidebar_img.size[0]}×{sidebar_img.size[1]}  →  {sidebar_path}")

    print("[5] 逐行检测 (row-local)...")
    annotated, row_details = annotate_sidebar(sidebar_img)
    ann_path = os.path.join(OUTPUT_DIR, "sidebar_annotated.png")
    annotated.save(ann_path)
    print(f"    ✓ 检测到 {len(row_details)} 行  →  {ann_path}")

    # ── 颜色图例 ──
    print()
    print("    图例：绿/蓝框=row_rect  黄框=badge_region  青框=name_region  红框=detected badge")

    print("\n" + "-" * 60)
    print("  逐行详情 (row-local)")
    print("-" * 60)
    unread_count = 0
    for d in row_details:
        badge = d["badge"]
        rgns = d["regions"]
        status = "  "
        if badge["has_unread"]:
            unread_count += 1
            if badge["badge_type"] == "count":
                status = f"🔴 {badge['unread_count']}"
            else:
                status = "🔴 dot"
        name_str = d["name"] if d["name"] else "(未识别)"
        badge_info = ""
        if badge["badge_rect"]:
            bb = badge["badge_rect"]
            badge_info = f"  badge_box=({bb.x},{bb.y},{bb.width},{bb.height})"
        print(f"  Row #{d['index']:2d}  {status:>10s}  {name_str}{badge_info}")
        print(f"          badge_region=({rgns.badge.x},{rgns.badge.y},{rgns.badge.width},{rgns.badge.height})"
              f"  name_region=({rgns.name.x},{rgns.name.y},{rgns.name.width},{rgns.name.height})")

    print(f"\n  有未读的行: {unread_count}")

    # ── scan_sidebar_once 汇总 ──
    print("\n" + "-" * 60)
    print("  scan_sidebar_once() 结果")
    print("-" * 60)
    unread_chats = scan_sidebar_once(window_img, only_unread=True)
    if not unread_chats:
        print("  (当前视野无未读会话)")
    for c in unread_chats:
        print(f"  {c.badge_type:>5s}  count={str(c.unread_count):>4s}  "
              f"conf={c.confidence:.2f}  name={c.name!r}")

    # ── 完整滚动扫描 ──
    print("\n" + "-" * 60)
    print("  list_unread_chats() — 滚动扫描 + 去重")
    print("-" * 60)
    driver.scroll_sidebar_to_top()
    time.sleep(0.3)
    all_chats = list_unread_chats(driver)
    if not all_chats:
        print("  (未发现任何未读会话)")
    for i, c in enumerate(all_chats):
        print(f"  [{i+1}]  {c.badge_type:>5s}  count={str(c.unread_count):>4s}  "
              f"conf={c.confidence:.2f}  name={c.name!r}")

    print(f"\n  共 {len(all_chats)} 个未读会话（去重后）")

    monitored = filter_chats_by_groups_to_monitor(all_chats, cfg.groups_to_monitor)
    print("\n" + "-" * 60)
    print(f"  按 config groups_to_monitor 过滤：{len(all_chats)} → {len(monitored)} 个")
    print("-" * 60)
    for i, c in enumerate(monitored):
        print(f"  [{i+1}]  {c.badge_type:>5s}  count={str(c.unread_count):>4s}  "
              f"conf={c.confidence:.2f}  name={c.name!r}")

    if args.click_first:
        print("\n" + "-" * 60)
        print("  --click-first：与 process_unread_chats_batch 相同点击 + 标题就绪检测")
        print("-" * 60)
        if not monitored:
            print("  (groups_to_monitor 过滤后无未读，跳过点击)")
        else:
            target = monitored[0]
            print(f"  目标: name={target.name!r}  badge={target.badge_type}  unread={target.unread_count}")
            res = click_into_chat(
                driver,
                target,
                timeout=args.click_timeout,
                max_retries=3,
            )
            print(f"  ready={res.ready}  detected_title={res.detected_title!r}  reason={res.reason!r}")
            if res.error:
                print(f"  error: {res.error}")
            win = driver.capture_wechat_window()
            hp = os.path.join(OUTPUT_DIR, "header_after_click.png")
            get_header_image(win).save(hp)
            print(f"  主标题带截图 → {hp}")
            lines = list_header_ocr_lines(win)
            print(f"  多 band OCR 行（去重）: {lines!r}")
            hint = target.name.strip() if target.name else ""
            picked = extract_chat_header_title(win, match_hint=hint or None)
            print(f"  extract_chat_header_title(match_hint={hint!r}) → {picked!r}")

    # ── 全窗口标注 ──
    print("\n[6] 生成全窗口标注图...")
    full_ann = window_img.copy()
    draw = ImageDraw.Draw(full_ann)
    draw.rectangle(
        [sidebar_rect.x, sidebar_rect.y, sidebar_rect.x2, sidebar_rect.y2],
        outline="lime", width=3,
    )
    full_ann_path = os.path.join(OUTPUT_DIR, "window_annotated.png")
    full_ann.save(full_ann_path)
    print(f"    ✓ {full_ann_path}")

    print("\n" + "=" * 60)
    print(f"  完成！所有输出在 {os.path.abspath(OUTPUT_DIR)}/")
    print("=" * 60)


if __name__ == "__main__":
    main()
