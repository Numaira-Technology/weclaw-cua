"""screenshot command — capture WeChat window screenshots for agent processing.

Usage:
    weclaw screenshot sidebar         # sidebar crop + classification prompt
    weclaw screenshot chat            # current chat panel
    weclaw screenshot full            # full window
    weclaw screenshot scroll-capture  # scroll up + stitch current chat
"""

import os
import sys
import time

import click

from ..output.formatter import output


@click.group("screenshot")
@click.pass_context
def screenshot(ctx):
    """Capture WeChat window screenshots (no LLM needed).

    \b
    Use these commands to capture specific parts of WeChat.
    The agent sends the output images to its own vision LLM.
    """
    pass


@screenshot.command("sidebar")
@click.option("--output-dir", default=None, help="Directory for output files (default: output/work)")
@click.option("--format", "fmt", default="json", type=click.Choice(["json", "text"]))
@click.pass_context
def screenshot_sidebar(ctx, output_dir, fmt):
    """Screenshot the sidebar and output with classification prompt."""
    from ..context import load_app_context
    app = load_app_context(ctx)
    if app["root"] not in sys.path:
        sys.path.insert(0, app["root"])

    if not output_dir:
        output_dir = os.path.join(app["output_dir"], "work")
    os.makedirs(output_dir, exist_ok=True)

    pid = _get_mac_pid(app["config"])
    from platform_mac.macos_window import activate_pid, capture_window_pid
    activate_pid(pid)
    time.sleep(0.3)
    full = capture_window_pid(pid)
    assert full, "Failed to capture window"

    sidebar_width = int(full.width * 0.3)
    sidebar = full.crop((0, 0, sidebar_width, full.height))

    img_path = os.path.join(output_dir, "sidebar.png")
    sidebar.save(img_path, format="PNG")

    from shared.vision_prompts import SIDEBAR_PROMPT
    prompt_path = os.path.join(output_dir, "sidebar.prompt.txt")
    with open(prompt_path, "w", encoding="utf-8") as f:
        f.write(SIDEBAR_PROMPT)

    result = {
        "image": os.path.abspath(img_path),
        "prompt_file": os.path.abspath(prompt_path),
        "prompt": SIDEBAR_PROMPT,
        "response_file": os.path.abspath(os.path.join(output_dir, "sidebar.response.txt")),
        "instructions": "Send sidebar.png with the prompt to your vision LLM. Write the JSON response to sidebar.response.txt.",
    }
    output(result, fmt)


@screenshot.command("chat")
@click.option("--output-dir", default=None)
@click.option("--format", "fmt", default="json", type=click.Choice(["json", "text"]))
@click.pass_context
def screenshot_chat(ctx, output_dir, fmt):
    """Screenshot the current chat panel."""
    from ..context import load_app_context
    app = load_app_context(ctx)
    if app["root"] not in sys.path:
        sys.path.insert(0, app["root"])

    if not output_dir:
        output_dir = os.path.join(app["output_dir"], "work")
    os.makedirs(output_dir, exist_ok=True)

    pid = _get_mac_pid(app["config"])
    from platform_mac.macos_window import activate_pid, capture_window_pid
    activate_pid(pid)
    time.sleep(0.3)
    full = capture_window_pid(pid)
    assert full, "Failed to capture window"

    x1 = int(full.width * 0.31)
    y1 = 50
    x2 = int(full.width * 0.95)
    y2 = full.height - 50
    panel = full.crop((x1, y1, x2, y2))

    img_path = os.path.join(output_dir, "chat_panel.png")
    panel.save(img_path, format="PNG")

    from shared.vision_prompts import CHAT_PANEL_PROMPT
    prompt_path = os.path.join(output_dir, "chat_panel.prompt.txt")
    with open(prompt_path, "w", encoding="utf-8") as f:
        f.write(CHAT_PANEL_PROMPT)

    result = {
        "image": os.path.abspath(img_path),
        "prompt_file": os.path.abspath(prompt_path),
        "prompt": CHAT_PANEL_PROMPT,
        "response_file": os.path.abspath(os.path.join(output_dir, "chat_panel.response.txt")),
    }
    output(result, fmt)


@screenshot.command("scroll-capture")
@click.option("--scrolls", default=10, help="Number of scroll-up actions")
@click.option("--output-dir", default=None)
@click.option("--format", "fmt", default="json", type=click.Choice(["json", "text"]))
@click.pass_context
def screenshot_scroll_capture(ctx, scrolls, output_dir, fmt):
    """Scroll up in current chat, capture frames, stitch, and output."""
    from ..context import load_app_context
    app = load_app_context(ctx)
    if app["root"] not in sys.path:
        sys.path.insert(0, app["root"])

    if not output_dir:
        output_dir = os.path.join(app["output_dir"], "work")
    os.makedirs(output_dir, exist_ok=True)

    pid = _get_mac_pid(app["config"])
    from platform_mac.macos_window import activate_pid, capture_window_pid, main_window_bounds
    import pyautogui

    activate_pid(pid)
    time.sleep(0.3)

    frames = []
    for i in range(scrolls):
        activate_pid(pid)
        time.sleep(0.08)
        left, top, right, bottom = main_window_bounds(pid)
        mx = left + int((right - left) * 0.65)
        my = top + int((bottom - top) * 0.5)
        pyautogui.moveTo(mx, my, duration=0.1)
        pyautogui.scroll(500)
        time.sleep(1.15)
        shot = capture_window_pid(pid)
        if shot:
            frames.append(shot)

    if not frames:
        output({"error": "No frames captured"}, fmt)
        return

    frames.reverse()
    from utils.image_stitcher import stitch_screenshots
    from shared.vision_prompts import CHAT_PANEL_PROMPT

    chunk_size = 5
    chunks = [frames[i:i + chunk_size] for i in range(0, len(frames), chunk_size)]
    output_files = []

    for i, chunk in enumerate(chunks):
        stitched = stitch_screenshots(images=chunk, scroll_region=None)
        if not stitched:
            continue
        img_path = os.path.join(output_dir, f"stitched_{i:02d}.png")
        stitched.save(img_path, format="PNG")
        output_files.append({
            "image": os.path.abspath(img_path),
            "chunk_index": i,
        })

    prompt_path = os.path.join(output_dir, "chat_panel.prompt.txt")
    with open(prompt_path, "w", encoding="utf-8") as f:
        f.write(CHAT_PANEL_PROMPT)

    result = {
        "frames_captured": len(frames),
        "chunks": len(output_files),
        "prompt_file": os.path.abspath(prompt_path),
        "prompt": CHAT_PANEL_PROMPT,
        "images": output_files,
    }
    output(result, fmt)


@screenshot.command("full")
@click.option("--output-dir", default=None)
@click.option("--format", "fmt", default="json", type=click.Choice(["json", "text"]))
@click.pass_context
def screenshot_full(ctx, output_dir, fmt):
    """Screenshot the full WeChat window."""
    from ..context import load_app_context
    app = load_app_context(ctx)
    if app["root"] not in sys.path:
        sys.path.insert(0, app["root"])

    if not output_dir:
        output_dir = os.path.join(app["output_dir"], "work")
    os.makedirs(output_dir, exist_ok=True)

    pid = _get_mac_pid(app["config"])
    from platform_mac.macos_window import activate_pid, capture_window_pid
    activate_pid(pid)
    time.sleep(0.3)
    full = capture_window_pid(pid)
    assert full, "Failed to capture window"

    img_path = os.path.join(output_dir, "full_window.png")
    full.save(img_path, format="PNG")

    result = {
        "image": os.path.abspath(img_path),
        "width": full.width,
        "height": full.height,
    }
    output(result, fmt)


def _get_mac_pid(config) -> int:
    from platform_mac.grant_permissions import ensure_permissions
    from platform_mac.find_wechat_window import find_wechat_window
    ensure_permissions()
    ww = find_wechat_window(config.wechat_app_name)
    return ww.pid
