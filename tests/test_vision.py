import os
import sys
import unittest

if sys.platform != "win32":
    raise unittest.SkipTest("Windows-only interactive UI test")

# Add project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from platform_win.find_wechat_window import find_wechat_window
from platform_win.vision import capture_window, OcrEngine


def test_ocr_wechat_window():
    """
    Tests the full vision pipeline: find, capture, and OCR.
    """
    print("[*] Running test: test_ocr_wechat_window")

    # 1. Find the WeChat window
    hwnd = find_wechat_window()
    assert hwnd, "Test failed: WeChat window not found."
    print(f"[+] WeChat window found with HWND: {hwnd}")

    # 2. Take a screenshot
    screenshot = capture_window(hwnd)
    assert screenshot is not None, "Test failed: Screenshot capture returned None."
    print(f"[+] Screenshot captured successfully. Image size: {screenshot.size}")

    # 3. Initialize OCR engine
    ocr_engine = OcrEngine()

    # 4. Recognize text
    print("[*] Performing OCR on the screenshot...")
    results = ocr_engine.recognize_text(screenshot)
    print(f"[+] OCR finished. Found {len(results)} text fragments.")

    # 5. Print results
    for (bbox, text, prob) in results:
        print(f'  - Detected text: "{text}" (Confidence: {prob:.2f}) at bbox: {bbox}')

    print("[*] Test finished successfully.")


if __name__ == "__main__":
    test_ocr_wechat_window()
