"""Orchestrate the full algo_a pipeline: find target chats, click, and scroll.

This new version uses an OCR-based driver.
"""

import sys
import os
import json
import time
from dataclasses import asdict
from types import SimpleNamespace
from typing import Any

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from algo_a.list_target_chats_win import _sidebar_names_match, list_target_chats
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


def _is_chat_name_match(ui_name: str, config_name: str) -> bool:
    """
    Compares a chat name from the UI with a name from the config,
    handling cases where the UI name is truncated with '...' and ignoring emojis.
    """
    return _sidebar_names_match(ui_name, config_name)


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


def _row_has_unread(row: Any) -> bool:
    badge = getattr(row, "badge_text", None)
    if badge is None:
        return False
    s = str(badge).strip().lower()
    return bool(s) and s not in ("none", "null")


def _click_verify_extract_save(
    driver: Any,
    window: Any,
    config: WeclawConfig,
    matched_cfg: str,
    row: Any,
    written_paths: list[str],
) -> bool:
    chat = SimpleNamespace(name=row.name, ui_element=row)
    click_successful = False
    for attempt in range(3):
        print(
            f"[*] Attempting to click '{chat.name}' (lookup={matched_cfg!r}, "
            f"Attempt {attempt + 1}/3)"
        )
        driver.click_row(chat.ui_element, attempt=attempt)
        time.sleep(2)

        current_chat_name = driver.get_current_chat_name()
        if _is_chat_name_match(current_chat_name, matched_cfg):
            print(
                f"[+] Successfully clicked and verified chat: "
                f"current={current_chat_name!r}, target={matched_cfg!r}"
            )
            click_successful = True
            break
        print(
            f"[WARN] Click verification failed. Expected {matched_cfg!r}, "
            f"but current chat is {current_chat_name!r}. Retrying..."
        )

    if not click_successful:
        print(
            f"[ERROR] Failed to click on chat '{chat.name}' after 3 attempts."
        )
        return False

    messages = driver.get_chat_messages(chat.name)
    if not messages:
        print(f"[WARN] No messages were extracted from '{chat.name}'.")
    else:
        safe_filename = "".join(c for c in chat.name if c.isalnum() or c in (" ", "_")).rstrip()
        output_path = os.path.join(config.output_dir, f"{safe_filename}.json")
        with open(output_path, "w", encoding="utf-8") as f:
            messages_as_dict = []
            for msg in messages:
                d = asdict(msg)
                d["chat_name"] = chat.name
                d["sender"] = d["sender"] or ""
                messages_as_dict.append(d)
            json.dump(messages_as_dict, f, ensure_ascii=False, indent=2)
        print(f"[SUCCESS] Successfully saved {len(messages)} messages to {output_path}")
        written_paths.append(output_path)
    return True


def _find_first_visible_config_match(
    driver,
    window: Any,
    pending_names: list[str],
    unread_only: bool,
) -> tuple[str, Any] | None:
    rows = driver.get_sidebar_rows(window)
    print(
        f"[DEBUG] Named-chat filter scanning {len(rows)} visible row(s). "
        f"unread_only_config={unread_only}; name matches do not require unread"
    )
    for idx, row in enumerate(rows):
        badge = getattr(row, "badge_text", None)
        is_group = getattr(row, "is_group", None)
        bbox = getattr(row, "bbox", None)
        ui_name = str(getattr(row, "name", "") or "").strip()
        print(
            f"[DEBUG] Filter row #{idx:02d}: name={ui_name!r} badge={badge!r} "
            f"is_group={is_group!r} bbox={bbox!r}"
        )
        if not ui_name:
            print(f"[DEBUG] Filter row #{idx:02d}: reject empty_name")
            continue
        for cfg_name in pending_names:
            match = _is_chat_name_match(ui_name, cfg_name)
            print(
                f"[DEBUG] Filter row #{idx:02d}: compare ui={ui_name!r} "
                f"target={cfg_name!r} name_match={match}"
            )
            if match:
                print(f"[DEBUG] Filter row #{idx:02d}: selected target={cfg_name!r}")
                return cfg_name, row
        print(f"[DEBUG] Filter row #{idx:02d}: reject no_name_match")
    return None


def run_pipeline_a(config: WeclawConfig, vision_backend=None) -> list[str]:
    """Run the full message collection pipeline. Return paths to written JSON files."""
    assert config is not None

    if sys.platform == "darwin" and config.sidebar_unread_only:
        from algo_a.pipeline_a_mac_nav import run_pipeline_a_mac_nav

        return run_pipeline_a_mac_nav(config, vision_backend=vision_backend)

    os.makedirs(config.output_dir, exist_ok=True)
    written_paths: list[str] = []

    driver = _create_driver(vision_backend=vision_backend)
    if sys.platform == "darwin":
        driver.ensure_permissions()
    window = driver.find_wechat_window(config.wechat_app_name)
    if not window:
        print("[ERROR] Pipeline failed: Could not find WeChat window.")
        return written_paths

    uo = config.sidebar_unread_only
    if _groups_config_means_all_groups(config.groups_to_monitor):
        print(
            f"[*] Mode: ALL group chats (vision is_group). Unread filter: {uo}."
        )
        scroll_sidebar_to_top(driver, window)
        target_chats = list_target_chats(
            driver, window, all_groups=True, unread_only=uo
        )
        if not target_chats:
            print("[+] No target chats found. Pipeline finished.")
            return written_paths
        names_order = [c.name for c in target_chats]
        print(f"[+] Located {len(names_order)} target chat(s). Proceeding to click them.")

        max_locate_scrolls = 16
        for processed_num, matched_cfg in enumerate(names_order, start=1):
            print(f"\n--- Processing chat {processed_num}/{len(names_order)}: {matched_cfg!r} ---")
            scroll_sidebar_to_top(driver, window)
            scroll_attempts = 0
            row = None
            while scroll_attempts <= max_locate_scrolls:
                hit = _find_first_visible_config_match(
                    driver, window, [matched_cfg], unread_only=uo
                )
                if hit is not None:
                    _, row = hit
                    break
                scroll_attempts += 1
                print(
                    f"[*] Target not in viewport. Scrolling down "
                    f"({scroll_attempts}/{max_locate_scrolls})"
                )
                driver.scroll_sidebar(window, "down")
                time.sleep(1)

            if row is None:
                print(f"[WARN] Could not locate sidebar row for {matched_cfg!r}. Skipping.")
                continue

            ok = _click_verify_extract_save(
                driver, window, config, matched_cfg, row, written_paths
            )
            if not ok:
                print(f"[WARN] Click failed for {matched_cfg!r}. Skipping.")

        print("\n[SUCCESS] Pipeline finished processing all target chats.")
        return written_paths
    else:
        print(f"[*] Mode: named chats from config. Unread filter: {uo}.")
        pending = _dedupe_config_names(config.groups_to_monitor)
        print(f"[*] Pending config names: {pending!r}")
        if not pending:
            print("[+] No target chats found. Pipeline finished.")
            return written_paths

        scroll_sidebar_to_top(driver, window)
        scroll_attempts = 0
        max_scroll_attempts = 16
        processed_count = 0

        while pending and scroll_attempts <= max_scroll_attempts:
            hit = _find_first_visible_config_match(driver, window, pending, unread_only=uo)
            if hit is None:
                scroll_attempts += 1
                print(f"[*] No pending target in current viewport. Scrolling down ({scroll_attempts}/{max_scroll_attempts})")
                driver.scroll_sidebar(window, "down")
                time.sleep(1)
                continue

            matched_cfg, row = hit
            processed_count += 1
            print(f"\n--- Processing chat {processed_count}: lookup={matched_cfg!r}, seen={row.name!r} ---")

            ok = _click_verify_extract_save(
                driver, window, config, matched_cfg, row, written_paths
            )
            if not ok:
                print(
                    f"[ERROR] Failed to click on chat after 3 attempts. Keeping it pending."
                )
                driver.scroll_sidebar(window, "down")
                time.sleep(1)
                continue

            pending = [n for n in pending if n != matched_cfg]
            print(f"[*] Completed and removed from pending: {matched_cfg!r}; remaining={pending!r}")
            scroll_sidebar_to_top(driver, window)
            scroll_attempts = 0

        if pending:
            print(f"[WARN] Unresolved config names (not found/verified): {pending!r}")

        print("\n[SUCCESS] Pipeline finished processing named targets.")
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
