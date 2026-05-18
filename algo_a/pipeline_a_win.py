"""Orchestrate the full algo_a pipeline: find target chats, click, and scroll.

This new version uses an OCR-based driver.
"""

import sys
import os
import re
import time
from typing import Any

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from algo_a.async_chat_extraction import (
    AsyncChatExtractionQueue,
    ChatWriteResult,
    make_async_queue,
    record_chat_write_results,
)
from algo_a.list_target_chats_win import (
    _normalize_chat_label,
    _sidebar_compact_compare,
    _sidebar_names_match,
)
from algo_a.sidebar_scroll_to_top import scroll_sidebar_to_top
from config.weclaw_config import WeclawConfig


def _create_driver(vision_backend=None):
    """Auto-detect the platform and return the appropriate PlatformDriver."""
    if sys.platform == "win32":
        from platform_win.driver import WinDriver

        return WinDriver(vision_backend=vision_backend)
    if sys.platform == "darwin":
        from platform_mac.mac_ai_driver import MacDriver

        return MacDriver(vision_backend=vision_backend)
    raise NotImplementedError(f"Platform {sys.platform} is not supported yet.")


def _groups_config_means_all_groups(names: list[str]) -> bool:
    if not names:
        return True
    return len(names) == 1 and str(names[0]).strip() == "*"


def _chat_type_allows_row(row: Any, chat_type: str) -> bool:
    assert chat_type in ("group", "private", "all")
    raw = getattr(row, "is_group", None)
    if raw is None:
        return True
    is_group = bool(raw)
    return (
        chat_type == "all"
        or (chat_type == "group" and is_group)
        or (chat_type == "private" and not is_group)
    )


def _sidebar_filter_rejection_reason(
    row: Any,
    unread_only: bool,
    chat_type: str,
) -> str | None:
    assert chat_type in ("group", "private", "all")
    if not _chat_type_allows_row(row, chat_type):
        return f"chat_type={chat_type!r}"
    if unread_only and getattr(row, "badge_text", None) is None:
        return "no_unread_badge"
    return None


def _is_chat_name_match(ui_name: str, config_name: str) -> bool:
    """
    Compares a chat name from the UI with a name from the config,
    handling cases where the UI name is truncated with '...' and ignoring emojis.

    Also reuse the richer mac-facing matchers from ``chat_panel_detector`` (contain /
    emoji-stripped core / OCR suffix quirks). The Win pipeline previously used only
    ``_sidebar_names_match``, which is stricter — users saw the chat after scrolling but
    the OCR row string did not satisfy that predicate, so rows were skipped with no click.
    """
    if _sidebar_names_match(ui_name, config_name):
        return True
    try:
        from platform_mac.chat_panel_detector import sidebar_name_matches_config_group, titles_match

        return bool(
            sidebar_name_matches_config_group(ui_name, config_name)
            or titles_match(ui_name, config_name)
        )
    except Exception:
        return False


def _dedupe_config_names(names: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in names:
        cfg = str(raw).strip()
        if not cfg or cfg in seen:
            continue
        seen.add(cfg)
        out.append(cfg)
    return out


def _safe_output_filename(chat_name: str, fallback: str) -> str:
    name = str(chat_name or "").strip() or fallback
    safe = "".join(c for c in name if c.isalnum() or c in (" ", "_")).rstrip()
    return safe or fallback


def _fast_capture_enabled(config: WeclawConfig) -> bool:
    return (
        _groups_config_means_all_groups(config.groups_to_monitor)
        and config.chat_type == "all"
        and not config.sidebar_unread_only
    )


def _normalized_chat_key(name: str) -> str:
    clean = re.sub(r"\s+", " ", str(name or "")).strip()
    return clean.casefold()


def _row_signature(rows: list[Any]) -> tuple[tuple[str, int], ...]:
    out: list[tuple[str, int]] = []
    for row in rows:
        name = _normalized_chat_key(getattr(row, "name", ""))
        bbox = getattr(row, "bbox", None) or (0, 0, 0, 0)
        y_center = (int(bbox[1]) + int(bbox[3])) // 2 if len(bbox) == 4 else 0
        out.append((name, y_center))
    return tuple(out)


def _get_fast_sidebar_rows(driver: Any, window: Any) -> list[Any]:
    getter = getattr(driver, "get_fast_sidebar_rows", None)
    assert getter is not None, "driver must implement get_fast_sidebar_rows for capture-all fast path"
    return getter(window)


def _capture_sidebar_chat_names(
    driver: Any,
    window: Any,
    max_scrolls: int,
) -> list[str]:
    capturer = getattr(driver, "capture_sidebar_chat_names", None)
    if capturer is None:
        print("[WARN] Driver has no stitched sidebar name capture; fast path will not prefilter OCR rows.")
        return []
    names = capturer(window, max_scrolls=max_scrolls)
    out: list[str] = []
    seen_keys: set[str] = set()
    for name in names:
        key = _normalized_chat_key(name)
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)
        out.append(str(name).strip())
    print(f"[+] Capture-all sidebar name whitelist contains {len(out)} unique name(s).")
    return out


def _row_allowed_by_initial_sidebar_names(
    row: Any,
    allowed_sidebar_names: list[str] | set[str],
) -> bool:
    if not allowed_sidebar_names:
        return True
    sidebar_name = str(getattr(row, "name", "") or "").strip()
    return any(_is_chat_name_match(sidebar_name, name) for name in allowed_sidebar_names)


def _resolve_current_chat_title(driver: Any, fallback: str) -> str:
    resolver = getattr(driver, "resolve_current_chat_title", None)
    if resolver is None:
        return fallback
    title = str(resolver(fallback=fallback) or "").strip()
    return title or fallback


def _focused_chat_surface_label(driver: Any) -> str:
    """Prefer header OCR only (no sidebar VLM) so fast OCR pipelines stay OCR-only."""
    return _resolve_current_chat_title(driver, "").strip()


def _compact_alignment_token(text: str) -> str:
    """Normalization for row↔title prefix checks (ellipsis, hyphen, stray dots)."""
    t = _sidebar_compact_compare(_normalize_chat_label(text)).replace("-", "").replace("_", "")
    while t.endswith("..."):
        t = t[:-3].rstrip()
    while t.endswith("…"):
        t = t[:-1].rstrip()
    while t and t[-1] in ".。．⋯":
        t = t[:-1]
    return t


def _surface_title_aligns_visible_sidebar_row(sidebar_row_name: str, surface_title: str) -> bool:
    """Reject titles_match bridging unrelated chats; keep truncated OCR + noisy stems."""
    a = _compact_alignment_token(surface_title)
    b = _compact_alignment_token(sidebar_row_name)
    if not a or not b:
        return False
    if a == b:
        return True
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    if len(short) < 3:
        return False
    return long.startswith(short)


def _get_ocr_sidebar_rows(driver: Any, window: Any) -> list[Any]:
    getter = getattr(driver, "get_fast_sidebar_rows", None)
    assert callable(getter), "driver must expose OCR/sidebar rows for named capture"
    return getter(window)


def _row_is_selected(row: Any) -> bool:
    return bool(getattr(row, "selected", False) or getattr(row, "is_selected", False))


def _title_matches_target(title: str | None, target: str) -> bool:
    if not title:
        return False
    t = str(title).strip()
    return bool(t) and _is_chat_name_match(t, target)


def _finish_async_extractions(
    extraction_queue: AsyncChatExtractionQueue,
    async_results: list[ChatWriteResult],
    written_paths: list[str],
) -> None:
    async_results.extend(extraction_queue.drain())
    record_chat_write_results(async_results, written_paths)


def _capture_or_queue_current_chat(
    driver: Any,
    config: WeclawConfig,
    chat_name: str,
    written_paths: list[str],
    *,
    output_index: int,
    skip_navigation_vlm: bool,
    extraction_queue: AsyncChatExtractionQueue | None,
    async_results: list[ChatWriteResult],
    persist_chat_name: str | None = None,
) -> bool:
    """persist_chat_name: config / user label for JSON file and rows; chat_name retained for capture."""
    assert extraction_queue is not None
    return extraction_queue.capture_and_submit(
        chat_name=chat_name,
        output_index=output_index,
        max_scrolls=config.chat_max_scrolls,
        recent_window_hours=getattr(config, "recent_window_hours", 0),
        skip_navigation_vlm=skip_navigation_vlm,
        persist_chat_name=persist_chat_name,
    )


def _click_verify_extract_save(
    driver: Any,
    window: Any,
    config: WeclawConfig,
    matched_cfg: str,
    row: Any,
    written_paths: list[str],
    *,
    output_index: int,
    extraction_queue: AsyncChatExtractionQueue | None,
    async_results: list[ChatWriteResult],
    allow_current_chat_vlm: bool = True,
) -> bool:
    del window
    chat_name = str(getattr(row, "name", "") or "").strip()
    click_successful = False
    already_selected = _row_is_selected(row)
    verified_title: str | None = None
    if already_selected:
        verified_title = _resolve_current_chat_title(driver, chat_name or matched_cfg)
        print(
            f"[+] Sidebar row {chat_name!r} is already selected/open; "
            "capturing without sidebar click."
        )
        click_successful = True
    else:
        for attempt in range(3):
            print(
                f"[*] Attempting to click '{chat_name}' (lookup={matched_cfg!r}, "
                f"Attempt {attempt + 1}/3)"
            )
            driver.click_row(row, attempt=attempt)
            time.sleep(2)

            title = _resolve_current_chat_title(driver, chat_name or matched_cfg)
            if _title_matches_target(title, matched_cfg):
                print(
                    f"[+] Successfully clicked and verified chat: "
                    f"header={title!r}, target={matched_cfg!r}"
                )
                verified_title = title
                click_successful = True
                break
            getter = getattr(driver, "get_current_chat_name", None)
            if allow_current_chat_vlm and callable(getter):
                current_chat_name = getter()
                if _title_matches_target(current_chat_name, matched_cfg):
                    print(
                        f"[+] Successfully clicked and verified chat: "
                        f"current={current_chat_name!r}, target={matched_cfg!r}"
                    )
                    verified_title = str(current_chat_name).strip()
                    click_successful = True
                    break
            print(
                f"[WARN] Click verification failed. Expected {matched_cfg!r}, "
                f"but header is {title!r}. Retrying..."
            )

    if not click_successful:
        print(
            f"[ERROR] Failed to click on chat '{chat_name}' after 3 attempts."
        )
        return False

    capture_name = verified_title or _resolve_current_chat_title(driver, chat_name or matched_cfg)
    _capture_or_queue_current_chat(
        driver,
        config,
        capture_name,
        written_paths,
        output_index=output_index,
        skip_navigation_vlm=True,
        extraction_queue=extraction_queue,
        async_results=async_results,
        persist_chat_name=matched_cfg,
    )
    return True


def _click_extract_save_fast(
    driver: Any,
    config: WeclawConfig,
    matched_cfg: str,
    row: Any,
    written_paths: list[str],
    *,
    output_index: int,
    extraction_queue: AsyncChatExtractionQueue | None,
    async_results: list[ChatWriteResult],
    allow_current_chat_vlm: bool = True,
) -> bool:
    sidebar_name = str(getattr(row, "name", "") or "").strip()
    print(f"[*] Fast-clicking named chat: lookup={matched_cfg!r}, seen={sidebar_name!r}")

    click_ok = False
    verified_title: str | None = None
    if _row_is_selected(row):
        verified_title = _resolve_current_chat_title(driver, sidebar_name or matched_cfg)
        print(
            f"[+] Sidebar row {sidebar_name!r} is already selected/open; "
            "capturing without sidebar click."
        )
        click_ok = True
    else:
        for attempt in range(3):
            driver.click_row(row, attempt=attempt)
            time.sleep(1.6)
            title = _resolve_current_chat_title(driver, sidebar_name or matched_cfg)
            if _title_matches_target(title, matched_cfg):
                verified_title = title
                click_ok = True
                break
            getter = getattr(driver, "get_current_chat_name", None)
            if allow_current_chat_vlm and callable(getter):
                alt = getter()
                if _title_matches_target(alt, matched_cfg):
                    verified_title = str(alt).strip()
                    click_ok = True
                    break
            print(
                f"[WARN] Fast click verify failed (attempt {attempt + 1}/3). "
                f"header={title!r}, target={matched_cfg!r}"
            )

    if not click_ok:
        print(
            f"[ERROR] Could not open chat {matched_cfg!r} after 3 clicks — "
            "check Accessibility for Terminal/Python, WeChat in foreground, "
            "and sidebar name matches the config string."
        )
        return False

    chat_name = verified_title or _resolve_current_chat_title(
        driver, sidebar_name or matched_cfg
    )
    ok = _capture_or_queue_current_chat(
        driver,
        config,
        chat_name,
        written_paths,
        output_index=output_index,
        skip_navigation_vlm=True,
        extraction_queue=extraction_queue,
        async_results=async_results,
        persist_chat_name=matched_cfg,
    )
    if not ok:
        print(f"[WARN] Fast named capture failed for {matched_cfg!r}.")
    return ok


def _find_first_visible_config_match(
    driver,
    window: Any,
    pending_names: list[str],
    unread_only: bool,
    chat_type: str = "all",
    *,
    prefer_fast_sidebar: bool = False,
) -> tuple[str, Any] | None:
    assert chat_type in ("group", "private", "all")
    if prefer_fast_sidebar and callable(getattr(driver, "get_fast_sidebar_rows", None)):
        rows = driver.get_fast_sidebar_rows(window)
    else:
        rows = driver.get_sidebar_rows(window)
    print(
        f"[DEBUG] Named-chat filter scanning {len(rows)} visible row(s). "
        f"unread_only={unread_only}; chat_type={chat_type!r}"
    )
    for idx, row in enumerate(rows):
        badge = getattr(row, "badge_text", None)
        is_group = getattr(row, "is_group", None)
        bbox = getattr(row, "bbox", None)
        ui_name = str(getattr(row, "name", "") or "").strip()
        print(
            f"[DEBUG] Filter row #{idx:02d}: name={ui_name!r} badge={badge!r} "
            f"is_group={is_group!r} selected={_row_is_selected(row)!r} bbox={bbox!r}"
        )
        if not ui_name:
            print(f"[DEBUG] Filter row #{idx:02d}: reject empty_name")
            continue
        rejection_reason = _sidebar_filter_rejection_reason(row, unread_only, chat_type)
        if rejection_reason is not None:
            print(f"[DEBUG] Filter row #{idx:02d}: reject {rejection_reason}")
            continue
        for cfg_name in pending_names:
            match = _is_chat_name_match(ui_name, cfg_name)
            print(
                f"[DEBUG] Filter row #{idx:02d}: compare ui={ui_name!r} "
                f"target={cfg_name!r} name_match={match}"
            )
            if match:
                if not _surface_title_aligns_visible_sidebar_row(ui_name, cfg_name):
                    print(
                        f"[DEBUG] Filter row #{idx:02d}: reject fuzzy_name_collision "
                        f"ui={ui_name!r} vs cfg={cfg_name!r}"
                    )
                    continue
                print(f"[DEBUG] Filter row #{idx:02d}: selected target={cfg_name!r}")
                return cfg_name, row
        print(f"[DEBUG] Filter row #{idx:02d}: reject no_name_match")
    return None


def _non_fast_max_sweeps() -> int:
    raw = os.environ.get("WECLAW_NON_FAST_MAX_SWEEPS", "").strip()
    if not raw:
        return 2
    value = int(raw)
    assert value >= 1, "WECLAW_NON_FAST_MAX_SWEEPS must be >= 1"
    return value


def _mark_processed_label(labels: list[str], keys: set[str], label: str) -> None:
    clean = str(label or "").strip()
    key = _normalized_chat_key(clean)
    if not key or key in keys:
        return
    keys.add(key)
    labels.append(clean)


def _label_already_processed(
    label: str,
    processed_labels: list[str],
    processed_keys: set[str],
) -> bool:
    clean = str(label or "").strip()
    key = _normalized_chat_key(clean)
    if not key:
        return True
    if key in processed_keys:
        return True
    return any(
        _surface_title_aligns_visible_sidebar_row(clean, seen)
        for seen in processed_labels
    )


def _first_named_ocr_match(
    rows: list[Any],
    pending: list[str],
    attempted: set[str],
) -> tuple[str, Any] | None:
    for row in rows:
        ui_name = str(getattr(row, "name", "") or "").strip()
        if not ui_name:
            continue
        for cfg_name in pending:
            if cfg_name in attempted:
                continue
            if not _is_chat_name_match(ui_name, cfg_name):
                continue
            if not _surface_title_aligns_visible_sidebar_row(ui_name, cfg_name):
                print(
                    f"[DEBUG] OCR named row rejected fuzzy collision: "
                    f"ui={ui_name!r} vs cfg={cfg_name!r}"
                )
                continue
            return cfg_name, row
    return None


def _first_wildcard_eligible_row(
    rows: list[Any],
    *,
    unread_only: bool,
    chat_type: str,
    processed_labels: list[str],
    processed_keys: set[str],
) -> Any | None:
    for row in rows:
        ui_name = str(getattr(row, "name", "") or "").strip()
        if not ui_name:
            continue
        if _label_already_processed(ui_name, processed_labels, processed_keys):
            continue
        rejection_reason = _sidebar_filter_rejection_reason(row, unread_only, chat_type)
        if rejection_reason is not None:
            print(
                f"[DEBUG] Wildcard row rejected by {rejection_reason}: "
                f"name={ui_name!r} badge={getattr(row, 'badge_text', None)!r} "
                f"is_group={getattr(row, 'is_group', None)!r}"
            )
            continue
        return row
    return None


def _capture_focused_named_if_present(
    driver: Any,
    config: WeclawConfig,
    pending: list[str],
    written_paths: list[str],
    *,
    output_index: int,
    extraction_queue: AsyncChatExtractionQueue,
    async_results: list[ChatWriteResult],
) -> tuple[list[str], int]:
    label = _focused_chat_surface_label(driver)
    if not label:
        return pending, 0
    matched = next((cfg for cfg in pending if _is_chat_name_match(label, cfg)), None)
    if matched is None:
        return pending, 0
    print(
        f"[+] Main panel already matches {matched!r} (surface={label!r}); "
        "capturing without sidebar click."
    )
    ok = _capture_or_queue_current_chat(
        driver,
        config,
        label,
        written_paths,
        output_index=output_index,
        skip_navigation_vlm=True,
        extraction_queue=extraction_queue,
        async_results=async_results,
        persist_chat_name=matched,
    )
    if not ok:
        return pending, 0
    return [name for name in pending if name != matched], 1


def _run_named_ocr_dynamic_sweep(
    driver: Any,
    window: Any,
    config: WeclawConfig,
    pending: list[str],
    written_paths: list[str],
    extraction_queue: AsyncChatExtractionQueue,
    async_results: list[ChatWriteResult],
) -> list[str]:
    sidebar_scrolls = config.sidebar_max_scrolls
    processed_count = 0
    attempted: set[str] = set()
    pending, focused_done = _capture_focused_named_if_present(
        driver,
        config,
        pending,
        written_paths,
        output_index=processed_count + 1,
        extraction_queue=extraction_queue,
        async_results=async_results,
    )
    processed_count += focused_done
    if not pending:
        return pending

    for sweep_idx in range(_non_fast_max_sweeps()):
        captured_this_sweep = 0
        print(
            f"[*] OCR named dynamic sweep {sweep_idx + 1}: "
            f"pending={pending!r}"
        )
        scroll_sidebar_to_top(driver, window, max_down_scrolls=sidebar_scrolls)
        seen_viewports: set[tuple[tuple[str, int], ...]] = set()
        for scan_idx in range(sidebar_scrolls + 1):
            while pending:
                rows = _get_ocr_sidebar_rows(driver, window)
                rows = [row for row in rows if str(getattr(row, "name", "") or "").strip()]
                if not rows:
                    print("[WARN] OCR named scan returned no rows for current viewport.")
                    break
                signature = _row_signature(rows)
                if signature in seen_viewports:
                    print("[*] OCR named scan reached a repeated viewport.")
                    break
                hit = _first_named_ocr_match(rows, pending, attempted)
                if hit is None:
                    seen_viewports.add(signature)
                    break

                matched_cfg, row = hit
                processed_count += 1
                ui_name = str(getattr(row, "name", "") or "").strip()
                print(
                    f"\n--- OCR processing named chat {processed_count}: "
                    f"lookup={matched_cfg!r}, seen={ui_name!r} ---"
                )
                ok = _click_extract_save_fast(
                    driver,
                    config,
                    matched_cfg,
                    row,
                    written_paths,
                    output_index=processed_count,
                    extraction_queue=extraction_queue,
                    async_results=async_results,
                    allow_current_chat_vlm=False,
                )
                if ok:
                    pending = [name for name in pending if name != matched_cfg]
                    captured_this_sweep += 1
                    print(
                        f"[*] Completed and removed from pending: "
                        f"{matched_cfg!r}; remaining={pending!r}"
                    )
                else:
                    attempted.add(matched_cfg)
                    print(f"[WARN] Failed OCR named capture for {matched_cfg!r}. Continuing scan.")
                if not pending:
                    break

            if not pending:
                break
            if scan_idx >= sidebar_scrolls:
                print(f"[*] Reached sidebar max scrolls ({sidebar_scrolls}).")
                break
            driver.scroll_sidebar(window, "down")
            time.sleep(0.8)

        if not pending or captured_this_sweep == 0:
            break

    return pending


def _run_named_filtered_dynamic_sweep(
    driver: Any,
    window: Any,
    config: WeclawConfig,
    pending: list[str],
    written_paths: list[str],
    extraction_queue: AsyncChatExtractionQueue,
    async_results: list[ChatWriteResult],
) -> list[str]:
    sidebar_scrolls = config.sidebar_max_scrolls
    processed_count = 0
    attempted: set[str] = set()

    for sweep_idx in range(_non_fast_max_sweeps()):
        captured_this_sweep = 0
        print(
            f"[*] Filtered named dynamic sweep {sweep_idx + 1}: "
            f"pending={pending!r}"
        )
        scroll_sidebar_to_top(driver, window, max_down_scrolls=sidebar_scrolls)
        for scan_idx in range(sidebar_scrolls + 1):
            while pending:
                pending_candidates = [name for name in pending if name not in attempted]
                if not pending_candidates:
                    break
                hit = _find_first_visible_config_match(
                    driver,
                    window,
                    pending_candidates,
                    unread_only=config.sidebar_unread_only,
                    chat_type=config.chat_type,
                )
                if hit is None:
                    break

                matched_cfg, row = hit
                processed_count += 1
                ui_name = str(getattr(row, "name", "") or "").strip()
                print(
                    f"\n--- Filtered processing named chat {processed_count}: "
                    f"lookup={matched_cfg!r}, seen={ui_name!r} ---"
                )
                ok = _click_extract_save_fast(
                    driver,
                    config,
                    matched_cfg,
                    row,
                    written_paths,
                    output_index=processed_count,
                    extraction_queue=extraction_queue,
                    async_results=async_results,
                )
                if ok:
                    pending = [name for name in pending if name != matched_cfg]
                    captured_this_sweep += 1
                    print(
                        f"[*] Completed and removed from pending: "
                        f"{matched_cfg!r}; remaining={pending!r}"
                    )
                else:
                    attempted.add(matched_cfg)
                    print(f"[WARN] Failed filtered named capture for {matched_cfg!r}. Continuing scan.")
                if not pending:
                    break

            if not pending:
                break
            if scan_idx >= sidebar_scrolls:
                print(f"[*] Reached sidebar max scrolls ({sidebar_scrolls}).")
                break
            driver.scroll_sidebar(window, "down")
            time.sleep(0.8)

        if not pending or captured_this_sweep == 0:
            break

    return pending


def _run_wildcard_filtered_dynamic_sweep(
    driver: Any,
    window: Any,
    config: WeclawConfig,
    written_paths: list[str],
    extraction_queue: AsyncChatExtractionQueue,
    async_results: list[ChatWriteResult],
) -> None:
    sidebar_scrolls = config.sidebar_max_scrolls
    processed_labels: list[str] = []
    processed_keys: set[str] = set()
    processed_count = 0

    for sweep_idx in range(_non_fast_max_sweeps()):
        captured_this_sweep = 0
        print(f"[*] Wildcard filtered dynamic sweep {sweep_idx + 1}.")
        scroll_sidebar_to_top(driver, window, max_down_scrolls=sidebar_scrolls)
        seen_viewports: set[tuple[tuple[str, int], ...]] = set()
        for scan_idx in range(sidebar_scrolls + 1):
            while True:
                rows = driver.get_sidebar_rows(window)
                rows = [row for row in rows if str(getattr(row, "name", "") or "").strip()]
                if not rows:
                    print("[WARN] Semantic wildcard scan returned no rows for current viewport.")
                    break
                signature = _row_signature(rows)
                if signature in seen_viewports:
                    print("[*] Semantic wildcard scan reached a repeated viewport.")
                    break
                row = _first_wildcard_eligible_row(
                    rows,
                    unread_only=config.sidebar_unread_only,
                    chat_type=config.chat_type,
                    processed_labels=processed_labels,
                    processed_keys=processed_keys,
                )
                if row is None:
                    seen_viewports.add(signature)
                    break

                sidebar_name = str(getattr(row, "name", "") or "").strip()
                processed_count += 1
                print(
                    f"\n--- Wildcard processing chat {processed_count}: "
                    f"sidebar={sidebar_name!r} ---"
                )
                ok = _click_verify_extract_save(
                    driver,
                    window,
                    config,
                    sidebar_name,
                    row,
                    written_paths,
                    output_index=processed_count,
                    extraction_queue=extraction_queue,
                    async_results=async_results,
                    allow_current_chat_vlm=True,
                )
                title = _resolve_current_chat_title(driver, sidebar_name)
                _mark_processed_label(processed_labels, processed_keys, sidebar_name)
                _mark_processed_label(processed_labels, processed_keys, title)
                if ok:
                    captured_this_sweep += 1
                else:
                    print(f"[WARN] Wildcard capture failed for {sidebar_name!r}.")

            if scan_idx >= sidebar_scrolls:
                print(f"[*] Reached sidebar max scrolls ({sidebar_scrolls}).")
                break
            driver.scroll_sidebar(window, "down")
            time.sleep(0.8)

        if captured_this_sweep == 0:
            print("[*] No new wildcard chats captured in full sweep. Stopping.")
            break


def _run_capture_all_fast_path(
    driver: Any,
    window: Any,
    config: WeclawConfig,
    written_paths: list[str],
) -> list[str]:
    extraction_queue = make_async_queue(driver, config.output_dir)
    async_results: list[ChatWriteResult] = []
    sidebar_scrolls = config.sidebar_max_scrolls
    scroll_sidebar_to_top(driver, window, max_down_scrolls=sidebar_scrolls)
    allowed_sidebar_names = _capture_sidebar_chat_names(
        driver,
        window,
        max_scrolls=sidebar_scrolls,
    )
    scroll_sidebar_to_top(driver, window, max_down_scrolls=sidebar_scrolls)
    seen_viewports: set[tuple[tuple[str, int], ...]] = set()
    processed_keys: set[str] = set()
    processed_count = 0

    for scan_idx in range(sidebar_scrolls + 1):
        rows = _get_fast_sidebar_rows(driver, window)
        rows = [row for row in rows if str(getattr(row, "name", "") or "").strip()]
        signature = _row_signature(rows)
        if not rows:
            print("[WARN] Fast sidebar scan returned no rows. Stopping capture-all sweep.")
            break
        if signature in seen_viewports:
            print("[*] Fast capture-all reached a repeated viewport. Stopping sweep.")
            break
        seen_viewports.add(signature)
        print(f"--- Fast capture-all viewport {scan_idx + 1}: {len(rows)} row(s) ---")

        for row in rows:
            sidebar_name = str(getattr(row, "name", "") or "").strip()
            if not sidebar_name:
                continue
            sidebar_key = _normalized_chat_key(sidebar_name)
            if not _row_allowed_by_initial_sidebar_names(row, allowed_sidebar_names):
                print(
                    "[*] Skipping OCR row not in initial sidebar name whitelist: "
                    f"{sidebar_name!r}"
                )
                continue
            if sidebar_key in processed_keys:
                print(f"[*] Skipping already processed sidebar row: {sidebar_name!r}")
                continue
            if _row_is_selected(row):
                print(
                    f"[+] Sidebar row {sidebar_name!r} is already selected/open; "
                    "capturing without sidebar click."
                )
            else:
                driver.click_row(row, attempt=0)
                time.sleep(0.8)
            chat_name = _resolve_current_chat_title(driver, sidebar_name)
            chat_key = _normalized_chat_key(chat_name) or sidebar_key
            if chat_key in processed_keys:
                print(f"[*] Skipping duplicate chat title: {chat_name!r}")
                processed_keys.add(sidebar_key)
                continue
            processed_count += 1
            print(
                f"\n--- Fast processing chat {processed_count}: "
                f"sidebar={sidebar_name!r}, title={chat_name!r} ---"
            )
            ok = _capture_or_queue_current_chat(
                driver,
                config,
                chat_name,
                written_paths,
                output_index=processed_count,
                skip_navigation_vlm=True,
                extraction_queue=extraction_queue,
                async_results=async_results,
            )
            processed_keys.add(sidebar_key)
            processed_keys.add(chat_key)
            if not ok:
                print(f"[WARN] Fast capture failed to extract messages from {chat_name!r}.")

        if scan_idx >= sidebar_scrolls:
            print(f"[*] Reached sidebar max scrolls ({sidebar_scrolls}). Stopping fast sweep.")
            break
        driver.scroll_sidebar(window, "down")
        time.sleep(0.8)

    print("\n[SUCCESS] Fast capture-all sweep finished.")
    _finish_async_extractions(extraction_queue, async_results, written_paths)
    return written_paths


def run_pipeline_a(config: WeclawConfig, vision_backend=None) -> list[str]:
    """Run the full message collection pipeline. Return paths to written JSON files."""
    assert config is not None

    if (
        sys.platform == "darwin"
        and config.sidebar_unread_only
        and config.chat_type == "group"
    ):
        from algo_a.pipeline_a_mac_nav import run_pipeline_a_mac_nav

        return run_pipeline_a_mac_nav(config, vision_backend=vision_backend)

    return _run_sidebar_scan_pipeline(config, vision_backend=vision_backend)


def _run_sidebar_scan_pipeline(config: WeclawConfig, vision_backend=None) -> list[str]:
    """Run the sidebar scan implementation used by Windows and macOS fallback."""

    os.makedirs(config.output_dir, exist_ok=True)
    written_paths: list[str] = []

    driver = _create_driver(vision_backend=vision_backend)
    if sys.platform == "darwin" and hasattr(driver, "ensure_permissions"):
        driver.ensure_permissions()
    window = driver.find_wechat_window(config.wechat_app_name)
    if not window:
        print("[ERROR] Pipeline failed: Could not find WeChat window.")
        return written_paths

    uo = config.sidebar_unread_only
    sidebar_scrolls = config.sidebar_max_scrolls
    chat_type = config.chat_type
    if _fast_capture_enabled(config):
        print("[*] Mode: true capture-all fast path (OCR sidebar sweep).")
        return _run_capture_all_fast_path(driver, window, config, written_paths)

    extraction_queue = make_async_queue(driver, config.output_dir)
    async_results: list[ChatWriteResult] = []

    if _groups_config_means_all_groups(config.groups_to_monitor):
        print(
            f"[*] Mode: wildcard chats. chat_type={chat_type!r}. Unread filter: {uo}."
        )
        _run_wildcard_filtered_dynamic_sweep(
            driver,
            window,
            config,
            written_paths,
            extraction_queue,
            async_results,
        )
        print("\n[SUCCESS] Pipeline finished processing wildcard targets.")
        _finish_async_extractions(extraction_queue, async_results, written_paths)
        return written_paths

    print(
        f"[*] Mode: named chats from config. chat_type={chat_type!r}. "
        f"Unread filter: {uo}."
    )
    pending = _dedupe_config_names(config.groups_to_monitor)
    print(f"[*] Pending config names: {pending!r}")
    if not pending:
        print("[+] No target chats found. Pipeline finished.")
        _finish_async_extractions(extraction_queue, async_results, written_paths)
        return written_paths

    if uo or chat_type != "all":
        print("[*] Named filters active; using classified sidebar rows.")
        pending = _run_named_filtered_dynamic_sweep(
            driver,
            window,
            config,
            pending,
            written_paths,
            extraction_queue,
            async_results,
        )
    else:
        print("[*] Named filters inactive; using OCR-only sidebar rows.")
        pending = _run_named_ocr_dynamic_sweep(
            driver,
            window,
            config,
            pending,
            written_paths,
            extraction_queue,
            async_results,
        )
    if pending:
        print(f"[WARN] Unresolved config names (not found/verified): {pending!r}")
        print(
            "[HINT] Paste exact sidebar strings from the logs, or set "
            'groups_to_monitor to [] or ["*"] for wildcard capture.'
        )

    print("\n[SUCCESS] Pipeline finished processing named targets.")
    _finish_async_extractions(extraction_queue, async_results, written_paths)
    return written_paths


if __name__ == "__main__":
    import os
    from config.weclaw_config import load_config

    if not os.path.exists('output'):
        os.makedirs('output')

    CONFIG_PATH = "config/config.json"

    print(f"[*] Loading configuration from: {CONFIG_PATH}")
    
    if not os.path.exists(CONFIG_PATH):
        print(f"[ERROR] Configuration file not found at '{CONFIG_PATH}'.")
        print("Please copy 'config.json.example' to 'config.json' and fill in your details.")
        sys.exit(1)

    try:
        config = load_config(CONFIG_PATH)
        print("[+] Configuration loaded successfully.")
    except Exception as e:
        print(f"[ERROR] Failed to load or parse configuration: {e}")
        sys.exit(1)

    print("\n" + "="*50)
    print("          Starting WeClaw Pipeline A")
    print("="*50 + "\n")

    try:
        run_pipeline_a(config)
    except Exception as e:
        print(f"\n[FATAL] An unexpected error occurred during the pipeline execution: {e}")
