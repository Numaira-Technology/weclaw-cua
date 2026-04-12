import ctypes
import time

import easyocr
import numpy as np
import win32api
import win32con
import win32gui
import win32process
import win32com.client
from PIL import Image, ImageGrab

from shared.vision_ai import VisionAI


class OcrEngine:
    """Singleton class to manage the EasyOCR reader instance."""
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            print("[*] Initializing EasyOCR engine...")
            # This will download the model on the first run
            cls._instance = super(OcrEngine, cls).__new__(cls)
            cls._instance.reader = easyocr.Reader(["ch_sim", "en"], gpu=False)
            print("[+] EasyOCR engine initialized.")
        return cls._instance

    def recognize_text(self, image: Image.Image) -> list[tuple[list[list[int]], str, float]]:
        """Recognize text from a PIL image.

        Args:
            image: The PIL image to process.

        Returns:
            A list of tuples, where each tuple contains:
            - Bounding box coordinates for the detected text.
            - The recognized text string.
            - The confidence score (float).
        """
        image_np = np.array(image)
        return self.reader.readtext(image_np)


# Set process DPI awareness to handle screen scaling
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
except AttributeError:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except AttributeError:
        print("[WARN] Could not set DPI awareness. Screenshot may be incorrect on high-DPI displays.")

user32 = ctypes.windll.user32



def _force_foreground_window(hwnd: int):
    """A multi-layered, forceful method to bring a window to the foreground."""

    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        time.sleep(0.2)

    # 1. Simple method
    try:
        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.2)
        if user32.GetForegroundWindow() == hwnd:
            return  # Success
    except Exception:
        pass  # Continue to more forceful methods

    # 2. The ALT key "SendKeys" hack
    try:
        shell = win32com.client.Dispatch("WScript.Shell")
        shell.SendKeys('%')  # Sends an ALT key press to unlock foreground activation
        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.2)
        if user32.GetForegroundWindow() == hwnd:
            return  # Success
    except Exception as e:
        print(f"[WARN] SendKeys activation hack failed: {e}")

    # 3. The AttachThreadInput method (last resort)
    try:
        foreground_thread_id = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
        target_thread_id, _ = win32process.GetWindowThreadProcessId(hwnd)

        if foreground_thread_id != target_thread_id:
            win32process.AttachThreadInput(foreground_thread_id, target_thread_id, True)

        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

        win32gui.SetForegroundWindow(hwnd)
        win32gui.ShowWindow(hwnd, win32con.SW_SHOW)

        if foreground_thread_id != target_thread_id:
            win32process.AttachThreadInput(foreground_thread_id, target_thread_id, False)

        time.sleep(0.2)
    except Exception as e:
        print(f"[WARN] AttachThreadInput activation failed: {e}")


def capture_window(hwnd: int, save_path: str = None) -> Image.Image | None:
    """Captures a screenshot of the specified window handle (HWND)."""
    if not hwnd or not user32.IsWindow(hwnd):
        print(f"[ERROR] HWND {hwnd} is not a valid window.")
        return None

    # Use the more forceful method to bring the window to the front
    _force_foreground_window(hwnd)

    # After attempting to bring window to front, check if it was successful
    if user32.GetForegroundWindow() != hwnd:
        print(f"[ERROR] Failed to bring HWND {hwnd} to the foreground. Screenshot will likely be incorrect.")

    try:
        # Get initial window rect to check if it's off-screen
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        width = right - left
        height = bottom - top

        # If window is horizontally off-screen, move it to (0, top)
        if left < 0:
            print(f"[DEBUG] Window is off-screen at {left}. Moving it to 0.")
            win32gui.MoveWindow(hwnd, 0, top, width, height, True)
            time.sleep(0.3) # Give window time to move and redraw
        
        # After potentially moving, get the final, correct coordinates for the screenshot
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)

    except win32gui.error as e:
        print(f"[ERROR] Failed to get/move window rect for HWND {hwnd}: {e}")
        return None

    # Check if the window is off-screen or minimized
    if (right - left) <= 1 or (bottom - top) <= 1:
        print(f"[WARN] Window {hwnd} appears to be minimized, off-screen, or has invalid dimensions. Cannot capture.")
        return None

    # Capture the screen area defined by the rectangle
    print(f"[DEBUG] Capturing bbox: ({left}, {top}, {right}, {bottom})")
    try:
        screenshot = ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)
        print(f"[DEBUG] Captured bbox: ({left}, {top}, {right}, {bottom})")
        if save_path:
            screenshot.save(save_path)
        return screenshot
    except Exception as e:
        print(f"[FATAL_CAPTURE] Exception during ImageGrab.grab: {type(e).__name__}: {e}")
        return None
