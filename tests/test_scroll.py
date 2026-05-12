import os
import sys
import unittest
import time

if sys.platform != "win32":
    raise unittest.SkipTest("Windows-only interactive UI test")

# Add project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from platform_win.driver import WinDriver


def test_scroll_sidebar():
    """Tests the sidebar scrolling functionality."""
    print("[*] Running test: test_scroll_sidebar")

    driver = WinDriver()
    driver.find_wechat_window()

    print("\nFirst, scrolling DOWN. Check the WeChat window.")
    driver.scroll_sidebar(driver.hwnd, "down")
    time.sleep(2)  # Wait 2 seconds for you to observe

    print("\nNow, scrolling UP. Check the WeChat window again.")
    driver.scroll_sidebar(driver.hwnd, "up")
    time.sleep(2)

    print("\n[*] Test finished. Please verify if the scrolling occurred as expected.")


if __name__ == "__main__":
    test_scroll_sidebar()
