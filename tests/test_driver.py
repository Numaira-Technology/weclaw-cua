import os
import sys
import unittest

if sys.platform != "win32":
    raise unittest.SkipTest("Windows-only interactive UI tests")

# Add project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from platform_win.driver import WinDriver


import time

def test_get_sidebar_rows(driver):
    """Tests finding the sidebar, grouping rows, and extracting names/badges."""
    print("\n[*] Running test: test_get_sidebar_rows")

    # The 'window' argument is the HWND, which is stored in the driver instance
    sidebar_rows = driver.get_sidebar_rows(driver.hwnd)

    assert sidebar_rows, "Test failed: No rows were found in the sidebar."

    print(f"[+] Successfully found {len(sidebar_rows)} rows in the sidebar:")
    for i, row in enumerate(sidebar_rows):
        name = driver.get_row_name(row)
        badge = driver.get_row_badge_text(row)
        if badge:
            print(f'  - Row {i+1}: Detected Name = "{name}", Badge = "{badge}"')
        else:
            print(f'  - Row {i+1}: Detected Name = "{name}"')

        # for element in row.elements:
        #     text_preview = element.text.replace('\n', ' ') # Replace newlines for cleaner output
        #     print(f'    - OCR Element: "{text_preview}" (Confidence: {element.confidence:.2f})')

    # --- Test click_row --- #
    print("\n[*] Running test: test_click_row")
    if sidebar_rows:
        target_row = sidebar_rows[0]
        target_name = driver.get_row_name(target_row)
        print(f"[*] Attempting to click on the first row: '{target_name}'")
        driver.click_row(target_row)
        print("[+] Click action performed. Please verify visually.")
        time.sleep(3) # Pause for visual confirmation
    else:
        print("[WARN] No rows found, skipping click test.")

    print("\n[*] All tests finished successfully.")


def test_message_elements(driver):
    """Tests finding elements in the message panel."""
    print("\n[*] Running test: test_message_elements")

    message_elements = driver.get_message_elements(driver.hwnd)
    assert message_elements is not None, "get_message_elements should not return None"

    print(f"[+] Found {len(message_elements)} message elements:")
    for i, element in enumerate(message_elements):
        text_preview = element.text.replace('\n', ' ')
        print(f"  - Element {i+1}: \"{text_preview}\"")


def test_scroll_messages(driver):
    """Tests scrolling the message panel."""
    print("\n[*] Running test: test_scroll_messages")

    print("[*] Scrolling down...")
    driver.scroll_messages(driver.hwnd, "down")
    time.sleep(2)

    print("[*] Scrolling up...")
    driver.scroll_messages(driver.hwnd, "up")
    time.sleep(2)

    print("[+] Message scrolling test finished.")


if __name__ == "__main__":
    # Initialize WinDriver and find the WeChat window
    driver = WinDriver()
    driver.find_wechat_window()

    if driver.hwnd:
        test_get_sidebar_rows(driver)
        test_message_elements(driver)
        test_scroll_messages(driver) # Run the new test
    else:
        print("[ERROR] Test execution failed: WeChat window not found.")
