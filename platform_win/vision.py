import ctypes
from ctypes import wintypes
import time

import easyocr
import win32gui
import win32con
import win32process
import win32com.client
from PIL import Image, ImageGrab
import numpy as np


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


def capture_window(hwnd: int) -> Image.Image | None:
    """Captures a screenshot of the specified window handle (HWND)."""
    if not hwnd or not user32.IsWindow(hwnd):
        print(f"[ERROR] HWND {hwnd} is not a valid window.")
        return None

    # Use the more forceful method to bring the window to the front
    _force_foreground_window(hwnd)

    # After attempting to bring window to front, check if it was successful
    if user32.GetForegroundWindow() != hwnd:
        print(f"[ERROR] Failed to bring HWND {hwnd} to the foreground. Screenshot will likely be incorrect.")
        # We can choose to return None here, but for debugging, we'll proceed

    # Get window rectangle using DWM for better accuracy on modern apps
    left, top, right, bottom = 0, 0, 0, 0
    try:
        rect = wintypes.RECT()
        dwmapi = ctypes.windll.dwmapi
        DWMWA_EXTENDED_FRAME_BOUNDS = 9
        dwmapi.DwmGetWindowAttribute(
            wintypes.HWND(hwnd),
            wintypes.DWORD(DWMWA_EXTENDED_FRAME_BOUNDS),
            ctypes.byref(rect),
            ctypes.sizeof(rect)
        )
        left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
    except Exception as e:
        print(f"[WARN] DwmGetWindowAttribute failed: {e}. Falling back to GetWindowRect.")
        # Fallback to the older method if DWM fails
        try:
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        except win32gui.error as e2:
            print(f"[ERROR] Fallback GetWindowRect also failed for HWND {hwnd}: {e2}")
            return None

    # Check if the window is off-screen or minimized
    if (right - left) <= 1 or (bottom - top) <= 1:
        print(f"[WARN] Window {hwnd} appears to be minimized, off-screen, or has invalid dimensions. Cannot capture.")
        return None

    # Capture the screen area defined by the rectangle
    print(f"[DEBUG] Capturing bbox: ({left}, {top}, {right}, {bottom})")
    screenshot = ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)
    return screenshot
