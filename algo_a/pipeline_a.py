"""Orchestrate the full algo_a pipeline: find target chats, click, and scroll.

This new version uses an OCR-based driver.
"""

import sys
import time

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

        # Click into the chat
        # The ui_element from ChatInfo is a SidebarRow object for the new driver
        driver.click_row(chat.ui_element)
        print(f"[+] Clicked on '{chat.name}'. Pausing for UI to update...")
        time.sleep(3)  # Wait for the message panel to load

        # TODO: In the next step, we will implement message scraping here.
        print(f"[*] Skipping message scraping for '{chat.name}' for now.")

    print("\n[SUCCESS] Pipeline finished processing all unread target chats.")
