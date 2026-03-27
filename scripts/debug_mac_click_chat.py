#!/usr/bin/env python3
"""Mac click-into-chat 调试脚本 — 支持多个未读会话逐一点击。

流程：
  1. 扫描 sidebar 取所有未读会话
  2. 逐个：保存点击前截图 → 点击 → 等 ready → 保存点击后截图
  3. 每次点击后 rescan sidebar 获取最新 row_rect
  4. 打印汇总

输出到 debug_outputs/click/
  chat_0/  chat_1/  ...  每个子目录含 5 张调试图
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image, ImageDraw, ImageFont

from platform_mac.driver import MacDriver
from platform_mac.sidebar_detector import (
    ChatInfo, Rect,
    scan_sidebar_once,
)
from platform_mac.chat_panel_detector import (
    capture_right_panel, get_header_image,
)
from algo_a.click_into_chat import (
    ClickResult,
    click_chat_row,
    wait_chat_panel_ready,
    rescan_unread,
    _find_chat_by_name,
)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "debug_outputs", "click")
MAX_CHATS = 5


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _try_font(size: int = 18):
    for p in ["/System/Library/Fonts/PingFang.ttc",
              "/System/Library/Fonts/STHeiti Light.ttc",
              "/System/Library/Fonts/Helvetica.ttc"]:
        if os.path.isfile(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _draw_row(img: Image.Image, row_rect: Rect, label: str = "") -> Image.Image:
    out = img.copy()
    draw = ImageDraw.Draw(out)
    draw.rectangle([row_rect.x, row_rect.y, row_rect.x2, row_rect.y2],
                   outline="lime", width=3)
    if label:
        font = _try_font(20)
        draw.text((row_rect.x + 6, max(row_rect.y - 24, 2)), label, fill="lime", font=font)
    return out


def _click_one_chat(driver, target: ChatInfo, chat_dir: str,
                    max_retries: int = 1, timeout: float = 5.0) -> ClickResult:
    """点击单个会话并保存完整调试图。"""
    _ensure_dir(chat_dir)

    # 1. 点击前截图
    before_img = driver.capture_wechat_window()
    before_img.save(os.path.join(chat_dir, "1_before_click.png"))

    if target.row_rect is not None:
        annotated = _draw_row(before_img, target.row_rect, f"TARGET: {target.name}")
        annotated.save(os.path.join(chat_dir, "2_target_annotated.png"))

    # 2. 点击 + 等 ready（含重试）
    driver.activate_wechat()
    time.sleep(0.2)

    final_result: ClickResult | None = None

    for retry in range(1 + max_retries):
        if retry > 0:
            print(f"      重试第 {retry} 次：rescan sidebar...")
            time.sleep(0.3)
            fresh_img, fresh_wb = driver.capture_wechat_window_with_bounds()
            fresh_win = Rect(fresh_wb.x, fresh_wb.y, fresh_wb.width, fresh_wb.height)
            fresh_chats = scan_sidebar_once(fresh_img, only_unread=False,
                                            window_bounds=fresh_win)
            updated = _find_chat_by_name(fresh_chats, target.name)
            if updated is None:
                print(f"      ✗ sidebar 中未找到 {target.name!r}")
                final_result = ClickResult(
                    ready=False,
                    target_name=target.name,
                    retries_used=retry,
                    reason="retry_target_not_found",
                    error=f"重试第 {retry} 次: sidebar 中未找到 {target.name!r}",
                    detected_title=final_result.detected_title if final_result else "",
                    click_point=final_result.click_point if final_result else (0, 0),
                    attempts=(final_result.attempts if final_result else 0),
                )
                break
            target = updated

        cx, cy = click_chat_row(driver, target)
        print(f"      click ({cx},{cy})")
        time.sleep(0.3)

        result = wait_chat_panel_ready(driver, target.name, timeout=timeout)
        result.click_point = (cx, cy)
        result.retries_used = retry

        if result.ready:
            final_result = result
            break

        final_result = result

    assert final_result is not None

    # 3. 点击后截图
    after_img = driver.capture_wechat_window()
    after_img.save(os.path.join(chat_dir, "3_after_click.png"))

    panel = capture_right_panel(after_img)
    panel.save(os.path.join(chat_dir, "4_right_panel.png"))

    header = get_header_image(after_img)
    header.save(os.path.join(chat_dir, "5_header_crop.png"))

    return final_result


def main():
    _ensure_dir(OUTPUT_DIR)
    print("=" * 60)
    print("  WeChat Mac — Multi-Chat Click Debug")
    print("=" * 60)

    driver = MacDriver()
    driver.ensure_permissions()

    print("\n[1] 激活微信...")
    driver.activate_wechat()
    driver.scroll_sidebar_to_top()
    time.sleep(0.5)

    # ── 扫描所有未读 ──
    print("[2] 扫描 sidebar 未读会话...")
    img, wb = driver.capture_wechat_window_with_bounds()
    win_rect = Rect(wb.x, wb.y, wb.width, wb.height)

    unread_chats = scan_sidebar_once(img, only_unread=True, window_bounds=win_rect)
    print(f"    检测到 {len(unread_chats)} 个未读会话")

    if not unread_chats:
        all_chats = scan_sidebar_once(img, only_unread=False, window_bounds=win_rect)
        if not all_chats:
            print("    ✗ 没有检测到任何会话行，退出")
            return
        unread_chats = all_chats[:1]
        print(f"    (无未读，取第一个会话做测试: {unread_chats[0].name!r})")

    targets = unread_chats[:MAX_CHATS]
    for i, c in enumerate(targets):
        print(f"    [{i+1}] {c.name!r}  badge={c.badge_type}  count={c.unread_count}")

    # ── 逐个点击 ──
    print(f"\n[3] 逐个点击 {len(targets)} 个会话...\n")
    results: list[ClickResult] = []

    for idx in range(len(targets)):
        target = targets[idx]
        chat_dir = os.path.join(OUTPUT_DIR, f"chat_{idx}")
        print(f"  ── 会话 {idx+1}/{len(targets)}: {target.name!r} ──")

        result = _click_one_chat(driver, target, chat_dir)
        results.append(result)

        status = "✓ ready" if result.ready else "✗ FAIL"
        print(f"    {status}  detected={result.detected_title!r}")
        print(f"    attempts={result.attempts}  retries={result.retries_used}  reason={result.reason}")
        if result.error:
            print(f"    error: {result.error}")
        print(f"    图片 → {os.path.abspath(chat_dir)}/\n")

        # rescan 更新剩余目标的 row_rect
        if idx < len(targets) - 1:
            time.sleep(0.5)
            fresh = rescan_unread(driver)
            for j in range(idx + 1, len(targets)):
                old_name = targets[j].name
                updated = _find_chat_by_name(fresh, old_name)
                if updated is not None:
                    targets[j] = updated

    # ── 汇总 ──
    print("=" * 60)
    print("  结果汇总")
    print("=" * 60)
    success = sum(1 for r in results if r.ready)
    for i, r in enumerate(results):
        mark = "✓" if r.ready else "✗"
        print(f"  [{i+1}] {mark} {r.target_name!r} → {r.detected_title!r}"
              f"  (attempts={r.attempts}, retries={r.retries_used}, reason={r.reason})")
    print(f"\n  成功: {success}  失败: {len(results) - success}")
    print(f"  输出: {os.path.abspath(OUTPUT_DIR)}/")
    print("=" * 60)


if __name__ == "__main__":
    main()
