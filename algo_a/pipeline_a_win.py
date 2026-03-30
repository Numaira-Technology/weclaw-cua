"""Orchestrate the full algo_a pipeline: find target chats, click, and scroll.

This new version uses an OCR-based driver.
"""

import sys
import os
import json
import time
from dataclasses import asdict
import re

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from config.weclaw_config import WeclawConfig


def _create_driver():
    """Auto-detect the platform and return the appropriate PlatformDriver."""
    if sys.platform == "win32":
        from platform_win.driver import WinDriver
        return WinDriver()
    else:
        raise NotImplementedError(f"Platform {sys.platform} is not supported yet.")


def _strip_emojis_and_whitespace(text: str) -> str:
    """Removes emojis and leading/trailing whitespace from a string."""
    if not text:
        return ""
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F" 
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\U0001F900-\U0001F9FF"
        "\u2600-\u26FF" 
        "\u2700-\u27BF"
        "\uFE0F"
        "]+",
        flags=re.UNICODE)
    return emoji_pattern.sub(r'', text).strip()


def _is_chat_name_match(ui_name: str, config_name: str) -> bool:
    """
    Compares a chat name from the UI with a name from the config,
    handling cases where the UI name is truncated with '...' and ignoring emojis.
    """
    if not ui_name or not config_name:
        return False

    clean_ui_name = _strip_emojis_and_whitespace(ui_name)
    clean_config_name = _strip_emojis_and_whitespace(config_name)
    
    if clean_ui_name.endswith('...'):
        return clean_config_name.startswith(clean_ui_name[:-3])
    else:
        return clean_ui_name == clean_config_name


def run_pipeline_a(config: WeclawConfig) -> None:
    """Run the full message collection pipeline."""
    assert config is not None

    from algo_a.list_target_chats_win import list_target_chats

    driver = _create_driver()
    window = driver.find_wechat_window()
    if not window:
        print("[ERROR] Pipeline failed: Could not find WeChat window.")
        return

    print("[*] Scrolling sidebar to the top...")
    for _ in range(10):
        driver.scroll_sidebar(window, "up")
        time.sleep(0.1)

    print(f"[*] Searching for unread target chats: {config.groups_to_monitor}")
    unread_target_chats = list_target_chats(driver, window, config.groups_to_monitor)

    if not unread_target_chats:
        print("[+] No unread target chats found. Pipeline finished.")
        return

    print(f"[+] Located {len(unread_target_chats)} unread target chats. Proceeding to click them.")

    for i, chat in enumerate(unread_target_chats):
        print(f"\n--- Processing chat {i + 1}/{len(unread_target_chats)}: {chat.name} ---")

        click_successful = False
        for i in range(3):
            print(f"[*] Attempting to click '{chat.name}' (Attempt {i + 1}/3)")
            driver.click_row(chat.ui_element, attempt=i)
            time.sleep(2)

            current_chat_name = driver.get_current_chat_name()
            if _is_chat_name_match(current_chat_name, chat.name):
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

        safe_filename = "".join(c for c in chat.name if c.isalnum() or c in (' ', '_')).rstrip()
        output_path = f"output/{safe_filename}.json"

        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                messages_as_dict = [asdict(msg) for msg in messages]
                json.dump(messages_as_dict, f, ensure_ascii=False, indent=2)
            print(f"[SUCCESS] Successfully saved {len(messages)} messages to {output_path}")
        except Exception as e:
            print(f"[ERROR] Failed to save messages for '{chat.name}' to {output_path}. Exception: {e}")

    print("\n[SUCCESS] Pipeline finished processing all unread target chats.")


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
