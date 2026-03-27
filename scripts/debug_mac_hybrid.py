#!/usr/bin/env python3
"""混合方案调试脚本：AX menubar + Quartz 截图 + Vision OCR。

用法：
    cd /path/to/weclaw-main
    python3 scripts/debug_mac_hybrid.py

输出：
    1. AX menubar 树
    2. 微信窗口截图 → 保存到 artifacts/
    3. 左侧 sidebar OCR 结果
    4. 右侧聊天区 OCR 结果
"""

from __future__ import annotations

import os
import sys
import time

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

ARTIFACTS_DIR = os.path.join(PROJECT_ROOT, "artifacts", "captures")


def main() -> None:
    from platform_mac import create_driver
    from platform_mac.ocr import format_ocr_results
    from platform_mac.screenshot import crop_sidebar, crop_chat_area

    os.makedirs(ARTIFACTS_DIR, exist_ok=True)

    driver = create_driver()

    # ── 1. 权限 ─────────────────────────────────────────
    print("=" * 70)
    print("[1/5] 检查 macOS Accessibility 权限...")
    try:
        driver.ensure_permissions()
        print("  ✓ 权限已授予")
    except PermissionError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    # ── 2. 找窗口 ───────────────────────────────────────
    print()
    print("[2/5] 定位并激活微信窗口...")
    try:
        win = driver.find_wechat_window()
        print(f"  ✓ app={win.app_name}  pid={win.pid}  title={win.title!r}")
    except RuntimeError as e:
        print(f"  ✗ {e}", file=sys.stderr)
        sys.exit(1)

    driver.activate_wechat()
    time.sleep(0.3)

    # ── 3. AX Menubar ──────────────────────────────────
    print()
    print("[3/5] AX Menubar（已证实可读）...")
    print("-" * 70)
    print(driver.dump_menubar(max_depth=2))

    # ── 4. 截图 ────────────────────────────────────────
    print()
    print("[4/5] Quartz 窗口截图...")
    try:
        img, bounds = driver.capture_window()
        print(f"  ✓ 截图尺寸: {img.size[0]}×{img.size[1]} px")
        print(f"    窗口位置: ({bounds.x}, {bounds.y}, {bounds.width}, {bounds.height})")

        full_path = os.path.join(ARTIFACTS_DIR, "wechat_full.png")
        img.save(full_path)
        print(f"  → 完整截图已保存: {full_path}")

        sidebar_img = crop_sidebar(img)
        sidebar_path = os.path.join(ARTIFACTS_DIR, "wechat_sidebar.png")
        sidebar_img.save(sidebar_path)
        print(f"  → Sidebar 截图已保存: {sidebar_path}")

        chat_img = crop_chat_area(img)
        chat_path = os.path.join(ARTIFACTS_DIR, "wechat_chat.png")
        chat_img.save(chat_path)
        print(f"  → 聊天区截图已保存: {chat_path}")
    except Exception as e:
        print(f"  ✗ 截图失败: {e}", file=sys.stderr)
        sys.exit(1)

    # ── 5. OCR ─────────────────────────────────────────
    print()
    print("[5/5] Vision OCR 识别...")
    print()

    # Sidebar OCR
    print("── Sidebar (左侧会话列表) ──")
    print("-" * 70)
    try:
        from platform_mac.ocr import ocr_image
        sidebar_results = ocr_image(sidebar_img)
        print(format_ocr_results(sidebar_results, label="Sidebar"))
    except Exception as e:
        print(f"  ✗ Sidebar OCR 失败: {e}")

    print()

    # Chat area OCR
    print("── Chat Area (右侧聊天区) ──")
    print("-" * 70)
    try:
        chat_results = ocr_image(chat_img)
        print(format_ocr_results(chat_results, label="Chat"))
    except Exception as e:
        print(f"  ✗ Chat OCR 失败: {e}")

    # ── 总结 ────────────────────────────────────────────
    print()
    print("=" * 70)
    print("混合方案诊断完成。")
    print()
    print(f"截图保存在: {ARTIFACTS_DIR}/")
    print("  wechat_full.png     — 完整窗口")
    print("  wechat_sidebar.png  — 左侧 sidebar")
    print("  wechat_chat.png     — 右侧聊天区")
    print()
    if sidebar_results:
        print(f"Sidebar OCR: 识别到 {len(sidebar_results)} 条文本")
        print("  请检查是否包含群名/联系人名，以确认 sidebar 裁切比例正确。")
        print("  如果文本被截断或混入聊天区内容，请调整 screenshot.py 中的")
        print("  SIDEBAR_RIGHT 参数（当前=0.22）。")
    else:
        print("Sidebar OCR: 无结果——请检查 sidebar 截图是否正确。")

    if chat_results:
        print(f"Chat OCR: 识别到 {len(chat_results)} 条文本")
    else:
        print("Chat OCR: 无结果——可能当前没有打开聊天。")


if __name__ == "__main__":
    main()
