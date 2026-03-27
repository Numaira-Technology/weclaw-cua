#!/usr/bin/env python3
"""调试脚本：权限 + 找微信窗口 + 打印 AX UI tree（最小可验证闭环）。

用法：
    cd /path/to/weclaw-main
    python3 scripts/debug_mac_wechat_tree.py
"""

from __future__ import annotations

import os
import sys
import time

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from platform_mac import create_driver
from platform_mac.ui_tree_reader import (
    dump_tree,
    iter_children,
    get_attribute_safe,
    enable_enhanced_ui,
    get_content_from_sections,
)


def main() -> None:
    driver = create_driver()

    # ── Step 1: Accessibility 权限 ─────────────────────────
    print("=" * 70)
    print("[1/3] 检查 macOS Accessibility 权限...")
    try:
        driver.ensure_permissions()
        print("  ✓ 权限已授予")
    except PermissionError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"  ✗ 权限检查失败: {e}", file=sys.stderr)
        sys.exit(1)

    # ── Step 2: 定位微信窗口 ───────────────────────────────
    print()
    print("[2/3] 定位并激活微信窗口...")
    try:
        win = driver.find_wechat_window()
        print(f"  ✓ 找到微信窗口")
        print(f"    app_name : {win.app_name}")
        print(f"    pid      : {win.pid}")
        print(f"    title    : {win.title!r}")
    except RuntimeError as e:
        print(f"  ✗ {e}", file=sys.stderr)
        sys.exit(1)

    # 尝试启用 Enhanced UI
    print()
    print("  尝试启用 AXEnhancedUserInterface...")
    enable_enhanced_ui(win.ax_app)
    time.sleep(0.5)

    # ── Step 3: 打印 AX 树 ────────────────────────────────
    print()
    print("[3/3] 打印微信窗口 AX UI tree ...")

    # 方式 A: 标准 AXChildren
    print()
    print("── 方式 A: AXChildren (标准子节点) ──")
    print("-" * 70)
    tree_a = dump_tree(win.ax_window, max_depth=5)
    print(tree_a)

    # 统计有效节点
    direct_children = iter_children(win.ax_window)
    content_children = [
        c for c in direct_children
        if get_attribute_safe(c, "AXRole") not in ("AXButton", None)
    ]

    if not content_children:
        print()
        print("  ⚠ 微信窗口 AXChildren 只有标题栏按钮，无内容子节点。")
        print("    这是微信 macOS 版的已知限制——应用内部 UI 未通过")
        print("    标准 Accessibility API 暴露。")

    # 方式 B: AXSections
    print()
    print("── 方式 B: AXSections (Content Section) ──")
    content_el = get_content_from_sections(win.ax_window)
    if content_el:
        content_role = get_attribute_safe(content_el, "AXRole") or "?"
        content_title = get_attribute_safe(content_el, "AXTitle") or ""
        print(f"  找到 AXContent section: role={content_role} title={content_title!r}")

        sec_children = iter_children(content_el)
        non_btn = [c for c in sec_children if get_attribute_safe(c, "AXRole") not in ("AXButton", None)]
        if non_btn:
            print(f"  Content 下有 {len(non_btn)} 个非按钮子节点:")
            print("-" * 70)
            tree_b = dump_tree(content_el, max_depth=5)
            print(tree_b)
        else:
            print("  ⚠ AXContent section 指向窗口自身，无额外内容。")
    else:
        print("  未找到 AXSections / AXContent。")

    # 方式 C: App 级别遍历（menubar 等）
    print()
    print("── 方式 C: 应用级别子节点 (含 menubar) ──")
    print("-" * 70)
    tree_c = dump_tree(win.ax_app, max_depth=3, max_children=10)
    print(tree_c)

    # ── 总结 ──────────────────────────────────────────────
    print()
    print("=" * 70)
    print("诊断总结:")
    print(f"  窗口 AXChildren 数量: {len(direct_children)} (其中非按钮: {len(content_children)})")

    if not content_children:
        print()
        print("  结论: 微信 macOS 版未通过 AX API 暴露内部 UI。")
        print("  后续方案（按推荐度排序）:")
        print("    1. 使用 OCR / 截图 + 视觉识别 (screenshot-based)")
        print("    2. 使用 CGEvent 模拟键鼠 + 截图验证")
        print("    3. 检查是否有更新版本的微信暴露了 AX 信息")
        print("    4. 使用 Quartz CGWindowListCreateImage 截取窗口区域")
    else:
        print()
        print("  结论: 微信 UI 树已成功读取，可继续定位 sidebar / 聊天区。")
        print("  请关注:")
        print("    • AXSplitGroup — 左右分栏")
        print("    • AXScrollArea / AXTable — sidebar 列表")
        print("    • AXStaticText — 群名/消息文本")
        print("    • 带数字 value 的节点 — 未读 badge")


if __name__ == "__main__":
    main()
