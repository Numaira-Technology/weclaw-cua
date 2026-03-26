import ctypes
from ctypes import wintypes
import time
import json


import easyocr
import win32api
import win32gui
import win32con
import win32process
import win32com.client
from PIL import Image, ImageGrab
import numpy as np


from typing import Tuple

def _load_ai_config(config_path: str = "config/config.json") -> Tuple[str, str]:
    """Loads the AI API key and model name from the config file."""
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            api_key = config.get("openrouter_api_key", "").strip()
            model_name = config.get("llm_model", "").strip()
            if not api_key:
                raise ValueError("'openrouter_api_key' not found in config.json")
            if not model_name:
                raise ValueError("'llm_model' not found in config.json")
            return api_key, model_name
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Config file not found at: {config_path}. "
            "Please create it and add your 'openrouter_api_key' and 'llm_model'."
        )
    except json.JSONDecodeError:
        raise ValueError(f"Could not decode JSON from: {config_path}")


import openai
import base64
import io

import httpx

class VisionAI:
    """Singleton class to manage the Vision AI model instance via OpenRouter."""
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            print("[*] Initializing Vision AI model via OpenRouter...")
            cls._instance = super(VisionAI, cls).__new__(cls)
            try:
                api_key, model_name = _load_ai_config()

                # The OpenAI library is designed to handle the Authorization header automatically
                # when the api_key is provided.
                cls._instance.client = openai.OpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=api_key,
                )

                cls._instance.model_name = model_name
                print(f"[+] Vision AI client for model '{model_name}' initialized successfully.")
            except (ValueError, FileNotFoundError) as e:
                print(f"[ERROR] Failed to initialize Vision AI client: {e}")
                cls._instance.client = None
                cls._instance.model_name = None
        return cls._instance

    def query(self, prompt: str, image: Image.Image) -> str | None:
        """
        Sends a prompt and an image to the specified model via OpenRouter.

        Args:
            prompt: The text prompt to send to the model.
            image: The PIL image to be analyzed.

        Returns:
            The text response from the model, or None if an error occurs.
        """
        if not self.client:
            print("[ERROR] Vision AI client is not initialized. Cannot process query.")
            return None

        # Convert PIL Image to base64
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        base64_image = base64.b64encode(buffered.getvalue()).decode('utf-8')

        MAX_RETRIES = 3
        for attempt in range(MAX_RETRIES):
            print(f"[*] Sending query to Vision AI via OpenRouter... (Attempt {attempt + 1}/{MAX_RETRIES})")
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{base64_image}"
                                    }
                                },
                            ],
                        }
                    ],
                    max_tokens=2048,
                )
                print("[+] Received response from Vision AI.")

                if not response.choices:
                    print("[WARN] Vision AI response had no choices. Retrying...")
                    time.sleep(1)  # Wait before retrying
                    continue

                content = response.choices[0].message.content
                if not content:
                    print("[WARN] Vision AI response content was empty. Retrying...")
                    # Save the image that caused the empty response for debugging
                    image.save("debug_empty_response_capture.png")
                    print("[*] Saved problematic image to debug_empty_response_capture.png")
                    time.sleep(1)  # Wait before retrying
                    continue

                return content  # Success

            except Exception as e:
                print(f"[ERROR] An error occurred during the Vision AI query on attempt {attempt + 1}: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2)  # Wait a bit longer before retrying on exceptions
                else:
                    print("[ERROR] Max retries reached. Failing query.")
                    return None  # Failed after all retries

        return None  # Failed after all retries



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
        return screenshot
    except Exception as e:
        print(f"[FATAL_CAPTURE] Exception during ImageGrab.grab: {type(e).__name__}: {e}")
        return None
