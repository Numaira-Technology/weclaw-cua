"""Orchestrate the full algo_a pipeline: find target chats, click, and scroll.

This new version uses an OCR-based driver.
"""

import sys
import os
import json
import time
from dataclasses import asdict

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from algo_a.list_configured_chat_names import list_chats_by_configured_names
from algo_a.list_target_chats_win import _normalize_chat_label, list_target_chats
from algo_a.sidebar_scroll_to_top import scroll_sidebar_to_top
from config.weclaw_config import WeclawConfig


def _create_driver():
    """Auto-detect the platform and return the appropriate PlatformDriver."""
    if sys.platform == "win32":
        from platform_win.driver import WinDriver

        return WinDriver()
    if sys.platform == "darwin":
        from platform_mac.mac_ai_driver import MacDriver

        return MacDriver()
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
    if not ui_name or not config_name:
        return False

    clean_ui_name = _normalize_chat_label(ui_name)
    clean_config_name = _normalize_chat_label(config_name)
    
    if clean_ui_name.endswith('...'):
        return clean_config_name.startswith(clean_ui_name[:-3])
    else:
        return clean_ui_name == clean_config_name


def run_pipeline_a(config: WeclawConfig) -> list[str]:
    """Run the full message collection pipeline. Return paths to written JSON files."""
    assert config is not None

    if sys.platform == "darwin" and config.sidebar_unread_only:
        from algo_a.pipeline_a_mac_nav import run_pipeline_a_mac_nav

        return run_pipeline_a_mac_nav(config)

    os.makedirs(config.output_dir, exist_ok=True)
    written_paths: list[str] = []

    driver = _create_driver()
    if sys.platform == "darwin":
        driver.ensure_permissions()
    window = driver.find_wechat_window(config.wechat_app_name)
    if not window:
        print("[ERROR] Pipeline failed: Could not find WeChat window.")
        return written_paths

    scroll_sidebar_to_top(driver, window)

    uo = config.sidebar_unread_only
    if _groups_config_means_all_groups(config.groups_to_monitor):
        print(
            f"[*] Mode: ALL group chats (vision is_group). Unread filter: {uo}."
        )
        target_chats = list_target_chats(
            driver, window, all_groups=True, unread_only=uo
        )
    else:
        print(
            f"[*] Mode: named chats from config. Unread filter: {uo}."
        )
        print(f"[*] Config names: {config.groups_to_monitor!r}")
        target_chats = list_chats_by_configured_names(
            driver, window, config.groups_to_monitor, unread_only=uo
        )

    if not target_chats:
        if not _groups_config_means_all_groups(config.groups_to_monitor):
            print(
                "[HINT] No row matched those names. Example `Group A` is not a real WeChat title."
                " Set groups_to_monitor to [] or [\"*\"] to capture every group the model marks"
                " as is_group, or paste exact sidebar strings from your logs."
            )
        print("[+] No target chats found. Pipeline finished.")
        return written_paths

    print(f"[+] Located {len(target_chats)} target chat(s). Proceeding to click them.")

    for i, chat in enumerate(target_chats):
        print(f"\n--- Processing chat {i + 1}/{len(target_chats)}: {chat.name} ---")

        scroll_sidebar_to_top(driver, window)
        refreshed_matches = list_target_chats(driver, window, chat.name)
        if not refreshed_matches:
            print(f"[ERROR] Could not re-locate target chat '{chat.name}' before clicking. Skipping.")
            continue

        chat = refreshed_matches[0]

        click_successful = False
        for i in range(3):
            print(f"[*] Attempting to click '{chat.name}' (Attempt {i + 1}/3)")
            driver.click_row(chat.ui_element, attempt=i)
            time.sleep(2)

            current_chat_name = driver.get_current_chat_name()
            is_match = _is_chat_name_match(current_chat_name, chat.name)
            if is_match:
                print(f"[+] Successfully clicked and verified chat: '{chat.name}'")
                click_successful = True
                break
            else:
                print(f"[WARN] Click verification failed. Expected '{chat.name}', but current chat is '{current_chat_name}'. Retrying...")
        
        if not click_successful:
            print(f"[ERROR] Failed to click on chat '{chat.name}' after 3 attempts. Skipping.")
            continue

        messages = driver.get_chat_messages(chat.name)
        if not messages:
            print(f"[WARN] No messages were extracted from '{chat.name}'. Skipping save.")
            continue

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

    print("\n[SUCCESS] Pipeline finished processing all target chats.")
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
