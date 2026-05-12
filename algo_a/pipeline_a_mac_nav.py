"""macOS unread navigation pipeline.

Uses the left Messages navigation icon to jump through unread chats, then captures
each selected chat. Message VLM extraction is queued asynchronously when the
driver exposes capture/extract hooks.

Usage:
    from algo_a.pipeline_a_mac_nav import run_pipeline_a_mac_nav
    paths = run_pipeline_a_mac_nav(config)

Matching ``groups_to_monitor`` uses the **sidebar row label** from Vision / fast path
(``click_first_unread_sidebar_row``), not the header/title bar OCR.
"""

from __future__ import annotations

import os
import time
from typing import Any

from algo_a.async_chat_extraction import (
    ChatWriteResult,
    PendingChatWrite,
    make_async_queue,
    record_chat_write_results,
    write_chat_messages_json,
)
from algo_a.list_target_chats_win import _normalize_chat_label
from config.weclaw_config import WeclawConfig
from platform_mac.chat_panel_detector import sidebar_name_matches_config_group

_MAX_JUMPS = 200
_SAME_TITLE_BREAK = 5
_SETTLE_AFTER_DBL = 0.65


def _groups_config_means_all_groups(names: list[str]) -> bool:
    if not names:
        return True
    return len(names) == 1 and str(names[0]).strip() == "*"


def _allowed_chat_title(title: str, groups: list[str]) -> bool:
    if not title or not str(title).strip():
        return False
    if _groups_config_means_all_groups(groups):
        return True
    allowed = [g.strip() for g in groups if g and str(g).strip()]
    if not allowed:
        return False
    t = title.strip()
    return any(sidebar_name_matches_config_group(t, g) for g in allowed)


def _matching_config_chat_name(title: str, groups: list[str]) -> str | None:
    """If ``groups_to_monitor`` is an explicit allow-list, map resolved title onto the config string for output."""
    if not title or not str(title).strip():
        return None
    if _groups_config_means_all_groups(groups):
        return None
    allowed = [g.strip() for g in groups if g and str(g).strip()]
    if not allowed:
        return None
    t = title.strip()
    for g in allowed:
        if sidebar_name_matches_config_group(t, g):
            return g
    return None


def _finish_async_extractions(
    extraction_queue: Any,
    async_results: list[ChatWriteResult],
    written_paths: list[str],
) -> None:
    if extraction_queue is None:
        return
    async_results.extend(extraction_queue.drain())
    record_chat_write_results(async_results, written_paths)


def _capture_or_queue_chat(
    *,
    driver: Any,
    config: WeclawConfig,
    title: str,
    read_cap: int,
    output_index: int,
    written_paths: list[str],
    extraction_queue: Any,
    async_results: list[ChatWriteResult],
    persist_chat_name: str | None = None,
) -> bool:
    """``title``: window/header string for extraction; ``persist_chat_name``: config label for saved JSON."""
    label_for_jobs = persist_chat_name if persist_chat_name else title
    if extraction_queue is None:
        messages = driver.get_chat_messages(
            title,
            max_messages=read_cap,
            max_scrolls=config.chat_max_scrolls,
            recent_window_hours=getattr(config, "recent_window_hours", 0),
        )
        if not messages:
            print(f"[WARN] No messages were extracted from {title!r}.")
            return False
        output_path = write_chat_messages_json(
            output_dir=config.output_dir,
            chat_name=title,
            messages=messages,
            output_index=output_index,
            persist_chat_name=persist_chat_name,
        )
        print(f"[SUCCESS] Saved {len(messages)} messages to {output_path}")
        written_paths.append(output_path)
        return True

    captured = driver.capture_chat_messages(
        title,
        max_messages=read_cap,
        max_scrolls=config.chat_max_scrolls,
    )
    if getattr(captured, "chunks", None) == []:
        print(f"[WARN] No screenshots were captured for {title!r}.")
        return False
    async_results.extend(
        extraction_queue.submit(
            PendingChatWrite(
                output_index=output_index,
                chat_name=label_for_jobs,
                captured=captured,
                recent_window_hours=getattr(config, "recent_window_hours", 0),
            )
        )
    )
    return True


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

    print(
        "[*] macOS: unread via left Messages icon; sidebar row names from Vision "
        "(groups_to_monitor matches sidebar labels, not header OCR)."
    )

    if not driver.nav_messages_has_unread_badge():
        print("[+] No unread badge on the left Messages entry. Nothing to process.")
        return written_paths

    extraction_queue = make_async_queue(driver, config.output_dir)
    async_results: list[ChatWriteResult] = []
    jumps = 0
    same_title_run = 0
    last_title: str | None = None
    saved_keys: set[str] = set()
    processed_count = 0

    while driver.nav_messages_has_unread_badge() and jumps < _MAX_JUMPS:
        jumps += 1
        driver.double_click_messages_nav()
        time.sleep(_SETTLE_AFTER_DBL)
        read_cap, sidebar_clicked = driver.click_first_unread_sidebar_row()
        if read_cap is None:
            print("[WARN] Could not click an unread sidebar row; skipping this round.")
            continue

        title = str(sidebar_clicked or "").strip()
        if not title:
            print("[WARN] Sidebar row name empty; skipping (header OCR not used for monitoring).")
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

        if not _allowed_chat_title(title, config.groups_to_monitor):
            print(f"[*] Skipping out-of-scope chat: {title!r}")
            continue

        save_key = _normalize_chat_label(title) or title
        if save_key in saved_keys:
            print(f"[*] Chat already queued/saved; skipping duplicate: {title!r}")
            continue

        processed_count += 1
        persist = _matching_config_chat_name(title, config.groups_to_monitor)
        ok = _capture_or_queue_chat(
            driver=driver,
            config=config,
            title=title,
            read_cap=read_cap,
            output_index=processed_count,
            written_paths=written_paths,
            extraction_queue=extraction_queue,
            async_results=async_results,
            persist_chat_name=persist,
        )
        if ok:
            saved_keys.add(save_key)

    if jumps >= _MAX_JUMPS:
        print(f"[WARN] Reached max unread jumps ({_MAX_JUMPS}); stopping.")

    print("\n[SUCCESS] macOS unread navigation pipeline finished.")
    _finish_async_extractions(extraction_queue, async_results, written_paths)
    return written_paths
