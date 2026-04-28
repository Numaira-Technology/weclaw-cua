import os
import sys
import unittest

if sys.platform != "win32":
    raise unittest.SkipTest("Windows-only interactive UI test")

# Add project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from platform_win.vision import VisionAI, capture_window
from platform_win.find_wechat_window import find_wechat_window

def test_ai_vision_query():
    """
    Tests the full pipeline: find window, capture it, and send to Vision AI.
    """
    print("[*] --- Testing Vision AI Query --- [*]")

    # 1. Initialize the AI model (this will also load the key)
    ai = VisionAI()
    if not ai.client:
        print("[FAIL] AI model failed to initialize. Check previous error messages.")
        return

    # 2. Find the WeChat window
    print("\n[*] Step 1: Finding WeChat window...")
    hwnd = find_wechat_window()
    if not hwnd:
        print("[FAIL] WeChat window not found.")
        return
    print(f"[SUCCESS] Found WeChat window with HWND: {hwnd}")

    # 3. Capture a screenshot of the window
    print("\n[*] Step 2: Capturing window screenshot...")
    screenshot = capture_window(hwnd)
    if not screenshot:
        print("[FAIL] Failed to capture screenshot.")
        return
    
    # Save for debugging
    debug_path = "debug_ai_capture.png"
    screenshot.save(debug_path)
    print(f"[SUCCESS] Screenshot captured and saved to {debug_path}")

    # 4. Send to Vision AI with a simple prompt
    print("\n[*] Step 3: Sending to Vision AI for analysis...")
    prompt = "Describe this image in one sentence."
    response = ai.query(prompt, screenshot)

    if not response:
        print("[FAIL] Did not receive a response from the AI.")
        return

    print("\n--- AI Response ---")
    print(response)
    print("---------------------")
    print("\n[SUCCESS] Test finished.")

if __name__ == "__main__":
    test_ai_vision_query()
