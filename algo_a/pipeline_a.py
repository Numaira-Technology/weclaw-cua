"""Orchestrate the full algo_a pipeline: find target chats, click, and scroll.

This new version uses an OCR-based driver.
"""

import sys
import json
import time
from dataclasses import asdict

from config.weclaw_config import WeclawConfig


def _create_driver():
    """Auto-detect the platform and return the appropriate PlatformDriver."""
    if sys.platform == "win32":
        from platform_win.driver import WinDriver
        return WinDriver()
    else:
        # Placeholder for other platforms like macOS
        raise NotImplementedError(f"Platform {sys.platform} is not supported yet.")


def run_pipeline_a(config: WeclawConfig) -> None:
    """Run the full message collection pipeline."""
    assert config is not None

    from algo_a.list_target_chats import list_target_chats

    # 1. Initialize driver and find the WeChat window
    driver = _create_driver()
    window = driver.find_wechat_window()
    if not window:
        print("[ERROR] Pipeline failed: Could not find WeChat window.")
        return

    # 2. Scroll the sidebar to the top to ensure a consistent starting point.
    print("[*] Scrolling sidebar to the top...")
    for _ in range(10):  # Scroll up a few times to be sure
        driver.scroll_sidebar(window, "up")
        time.sleep(0.1)

    # 3. Scan the sidebar to find all unread chats from our target list.
    print(f"[*] Searching for unread target chats: {config.groups_to_monitor}")
    unread_target_chats = list_target_chats(driver, window, config.groups_to_monitor)

    if not unread_target_chats:
        print("[+] No unread target chats found. Pipeline finished.")
        return

    print(f"[+] Located {len(unread_target_chats)} unread target chats. Proceeding to click them.")

    # 4. For each found chat, click into it.
    # The message scraping logic will be added in a future step.
    for i, chat in enumerate(unread_target_chats):
        print(f"\n--- Processing chat {i + 1}/{len(unread_target_chats)}: {chat.name} ---")

        # Click into the chat with verification and retries
        click_successful = False
        for i in range(3): # Max 3 attempts
            print(f"[*] Attempting to click '{chat.name}' (Attempt {i + 1}/3)")
            driver.click_row(chat.ui_element)
            time.sleep(2) # Wait for UI to potentially update

            current_chat_name = driver.get_current_chat_name()
            # Simple comparison, might need to be more robust (e.g., handle truncated names)
            if current_chat_name and chat.name in current_chat_name:
                print(f"[+] Successfully clicked and verified chat: '{chat.name}'")
                click_successful = True
                break
            else:
                print(f"[WARN] Click verification failed. Expected '{chat.name}', but current chat is '{current_chat_name}'. Retrying...")
        
        # If all attempts failed, skip to the next chat
        if not click_successful:
            print(f"[ERROR] Failed to click on chat '{chat.name}' after 3 attempts. Skipping.")
            continue

        # 5. Scrape messages
        # TODO: Implement scrolling within the chat panel to get more history.
        messages = driver.get_chat_messages(chat.name)
        if not messages:
            print(f"[WARN] No messages were extracted from '{chat.name}'. Skipping save.")
            continue

        # 6. Save messages to a file
        # Sanitize chat name for filename
        safe_filename = "".join(c for c in chat.name if c.isalnum() or c in (' ', '_')).rstrip()
        output_path = f"output/{safe_filename}.json"

        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                # Convert list of dataclass objects to list of dicts
                messages_as_dict = [asdict(msg) for msg in messages]
                json.dump(messages_as_dict, f, ensure_ascii=False, indent=2)
            print(f"[SUCCESS] Successfully saved {len(messages)} messages to {output_path}")
        except Exception as e:
            print(f"[ERROR] Failed to save messages for '{chat.name}' to {output_path}. Exception: {e}")


    print("\n[SUCCESS] Pipeline finished processing all unread target chats.")
