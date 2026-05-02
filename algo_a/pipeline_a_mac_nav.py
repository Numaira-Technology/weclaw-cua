"""macOS：左侧「消息」图标双击依次跳入未读会话，替代侧栏反复滚动枚举。

Usage:
    from algo_a.pipeline_a_mac_nav import run_pipeline_a_mac_nav
    paths = run_pipeline_a_mac_nav(config)

Input spec:
    - WeclawConfig，且 sidebar_unread_only 为 True（未读驱动）。
    - 未读行列表来自 click_first_unread_sidebar_row：优先 get_fast_sidebar_rows
      （本机 Vision / scan_sidebar_once），无快路径时再 get_sidebar_rows。
    - groups_to_monitor 仅与本次侧栏行名比对，顶栏 OCR 不参与（避免误识消息预览等）。

Output spec:
    - 与 pipeline_a_win.run_pipeline_a 相同：写入的 JSON 路径列表；chat_name 与文件名
      使用本次点击的侧栏行名；顶栏 OCR 不参与写出与 groups_to_monitor。
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict

from algo_a.list_unread_chats import ocr_chat_allowed_by_groups_to_monitor
from algo_a.list_target_chats_win import _normalize_chat_label
from config.weclaw_config import WeclawConfig

_MAX_JUMPS = 200
_SAME_TITLE_BREAK = 5
_SETTLE_AFTER_DBL = 0.65


def _groups_config_means_all_groups(names: list[str]) -> bool:
    if not names:
        return True
    return len(names) == 1 and str(names[0]).strip() == "*"


def _allowed_sidebar_row_for_groups(sidebar_row_name: str, groups: list[str]) -> bool:
    """侧栏行名（未读跳转中通常为本机 Vision 快路径 OCR）是否与 groups_to_monitor 匹配。

    与 list_unread_chats / filter_chats_by_groups_to_monitor 使用同一套
    sidebar_name_matches_config_group 规则；不得传入顶栏 OCR 字符串。
    """
    if not sidebar_row_name or not str(sidebar_row_name).strip():
        return False
    if _groups_config_means_all_groups(groups):
        return True
    return ocr_chat_allowed_by_groups_to_monitor(sidebar_row_name.strip(), groups)


_allowed_chat_title = _allowed_sidebar_row_for_groups


def run_pipeline_a_mac_nav(config: WeclawConfig, vision_backend=None) -> list[str]:
    assert config.sidebar_unread_only
    if config.chat_type != "group":
        print(
            "[*] macOS unread navigation only supports group filtering reliably; "
            "falling back to sidebar scan for chat_type/private/all."
        )
        from algo_a.pipeline_a_win import _run_sidebar_scan_pipeline

        return _run_sidebar_scan_pipeline(config, vision_backend=vision_backend)
    os.makedirs(config.output_dir, exist_ok=True)
    written_paths: list[str] = []

    from platform_mac.mac_ai_driver import MacDriver

    driver = MacDriver(vision_backend=vision_backend)
    driver.ensure_permissions()
    window = driver.find_wechat_window(config.wechat_app_name)
    if not window:
        print("[ERROR] Pipeline failed: Could not find WeChat window.")
        return written_paths

    print("[*] macOS: 使用左侧消息图标双击依次处理未读（不滚侧栏枚举）；"
          "侧栏未读行用本机 Vision 快路径（get_fast_sidebar_rows）；"
          "写出与 groups_to_monitor 仅以侧栏行名为准（顶栏 OCR 不参与）。")

    if not driver.nav_messages_has_unread_badge():
        print("[+] 左侧消息入口无未读角标，无需处理。")
        return written_paths

    jumps = 0
    same_title_run = 0
    last_title: str | None = None
    saved_keys: set[str] = set()

    while driver.nav_messages_has_unread_badge() and jumps < _MAX_JUMPS:
        jumps += 1
        driver.double_click_messages_nav()
        time.sleep(_SETTLE_AFTER_DBL)
        read_cap, sidebar_clicked = driver.click_first_unread_sidebar_row()
        if read_cap is None:
            print("[WARN] 未能点击未读侧栏行，跳过本轮。")
            continue
        title = str(sidebar_clicked or "").strip()
        if not title:
            print(
                "[WARN] 侧栏行名为空，跳过（顶栏 OCR 不参与监控列表与写出文件名）。"
            )
            continue
        if title == last_title:
            same_title_run += 1
            if same_title_run >= _SAME_TITLE_BREAK:
                driver.clear_messages_nav_click_cache()
                same_title_run = 0
                last_title = None
            continue
        same_title_run = 0
        last_title = title

        if not _allowed_sidebar_row_for_groups(title, config.groups_to_monitor):
            print(f"[*] 跳过（不在监控范围）: {title!r}")
            continue

        save_key = _normalize_chat_label(title) or title
        if save_key in saved_keys:
            print(f"[*] 本会话已保存过，跳过重复写出: {title!r}")
            continue

        messages = driver.get_chat_messages(
            title,
            max_messages=read_cap,
            max_scrolls=config.chat_max_scrolls,
        )
        if not messages:
            print(f"[WARN] 未提取到消息，跳过保存: {title!r}")
            continue

        safe_filename = "".join(c for c in title if c.isalnum() or c in (" ", "_")).rstrip()
        output_path = os.path.join(config.output_dir, f"{safe_filename}.json")
        with open(output_path, "w", encoding="utf-8") as f:
            rows_out = []
            for msg in messages:
                d = asdict(msg)
                d["chat_name"] = title
                d["sender"] = d["sender"] or ""
                rows_out.append(d)
            json.dump(rows_out, f, ensure_ascii=False, indent=2)
        print(f"[SUCCESS] 已保存 {len(messages)} 条消息到 {output_path}")
        written_paths.append(output_path)
        saved_keys.add(save_key)

    if jumps >= _MAX_JUMPS:
        print(f"[WARN] 已达最大跳转次数 {_MAX_JUMPS}，停止。")

    print("\n[SUCCESS] macOS 未读跳转流水线结束。")
    return written_paths
