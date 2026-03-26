
import os
import sys
import time

# Add project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from platform_win.driver import WinDriver
from list_target_chats import load_target_chats

def main():
    """Main pipeline for finding and processing chats."""
    driver = WinDriver()
    driver.find_wechat_window()

    target_chats = load_target_chats()
    if not target_chats:
        print("[WARN] No target chats specified in config.json. Exiting.")
        return

    print(f"[*] Targets: {target_chats}")

    # --- Part 1: Scroll through the sidebar to find all target chats --- 
    found_chats = {}
    seen_chat_names = set()
    
    # Limit the number of scrolls to prevent infinite loops
    max_scrolls = 10 
    scroll_count = 0

    print("\n[*] Starting sidebar scan...")
    while len(found_chats) < len(target_chats) and scroll_count < max_scrolls:
        print(f"\n--- Scan Iteration {scroll_count + 1} ---")
        sidebar_rows = driver.get_sidebar_rows(driver.hwnd)
        
        current_visible_names = {driver.get_row_name(row) for row in sidebar_rows}

        # If we scroll and see the exact same chats, we're at the end
        if current_visible_names.issubset(seen_chat_names):
            print("[*] Reached the end of the chat list. No new chats found.")
            break

        newly_seen_chats = current_visible_names - seen_chat_names
        seen_chat_names.update(newly_seen_chats)
        print(f"[*] Found {len(newly_seen_chats)} new chats in this view.")

        for row in sidebar_rows:
            name = driver.get_row_name(row)
            if name in target_chats and name not in found_chats:
                found_chats[name] = row
                print(f"[+] Found target chat: '{name}'")

        if len(found_chats) == len(target_chats):
            print("[*] All target chats have been found.")
            break

        # Scroll down to find more chats
        driver.scroll_sidebar(driver.hwnd, "down")
        scroll_count += 1
        time.sleep(1) # Wait for UI to update after scroll

    print(f"\n[*] Sidebar scan finished. Found {len(found_chats)} out of {len(target_chats)} targets.")

    # --- Part 2: Click into each found chat and scroll up --- 
    if not found_chats:
        print("[WARN] No target chats were found. Cannot proceed.")
        return

    print("\n[*] Processing found chats...")
    for name, row in found_chats.items():
        print(f"\n--- Processing '{name}' ---")
        
        # 1. Click the chat row
        print(f"[*] Clicking on '{name}'...")
        driver.click_row(row)
        time.sleep(2) # Wait for chat to open

        # 2. Scroll up to get history
        print(f"[*] Scrolling up in '{name}' to load history...")
        for i in range(3): # Scroll up 3 times as a demo
            driver.scroll_messages(driver.hwnd, "up")
            print(f"  - Scroll up ({i+1}/3)")
            time.sleep(1)
        
        print(f"[+] Finished processing '{name}'.")

    print("\n[*] Pipeline finished.")

if __name__ == "__main__":
    main()
