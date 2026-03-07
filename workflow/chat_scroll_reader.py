"""
Multi-pass scroll reader for the WeChat chat window (step 5).

Reads all unread messages by scrolling down until no new content appears,
using PIL screenshot diff to detect when the bottom has been reached.
Dispatches by OS: Windows crops vision queries to the chat content region and
uses a hard-coded screen coord to click the banner; macOS sends full screenshots
(same as all other Mac vision steps) and uses the AX tree to dismiss the banner.

Usage:
    suspects, screenshots = await read_messages_with_scroll(
        computer, model, thread_name, thread_id,
        capture_dir, settings, max_passes=4, scroll_clicks=5
    )

Input:
    - computer:      Computer instance (connected)
    - model:         LiteLLM model string
    - thread_name:   Display name of the group chat (used for capture filenames)
    - thread_id:     Unique ID of the thread
    - capture_dir:   Path where screenshots are saved
    - settings:      ComputerSettings — os_type selects the banner-dismiss path and
                     vision query strategy
    - max_passes:    Hard cap on scroll iterations (default 4)
    - scroll_clicks: Scroll notches per pass (used on macOS and Windows wheel fallback)

Output:
    - suspects:     List of dicts [{sender_id, sender_name, evidence_text}], deduplicated
    - screenshots:  All screenshot Paths captured during the loop
"""

from __future__ import annotations

import asyncio
import io
from pathlib import Path
from typing import Dict, List, Tuple, TYPE_CHECKING

from PIL import Image, ImageChops

from modules.banner_checker import banner_check_prompt, parse_banner_response
from modules.crop_utils import get_regions
from modules.message_reader import message_reader_prompt, parse_reader_response
from modules.scroll_actions import scroll_chat_window_down

if TYPE_CHECKING:
    from runtime.computer_session import ComputerSettings


def _crop_bytes(screenshot_bytes: bytes, region) -> bytes:
    return region.crop_image(screenshot_bytes)


def _at_bottom(before_bytes: bytes, after_bytes: bytes) -> bool:
    """Return True if the chat content did not move after scrolling."""
    img_before = Image.open(io.BytesIO(before_bytes))
    img_after = Image.open(io.BytesIO(after_bytes))
    diff = ImageChops.difference(img_before, img_after)
    return diff.getbbox() is None


def _dedup_suspects(suspects: List[Dict]) -> List[Dict]:
    seen = {}
    for s in suspects:
        sid = s.get("sender_id", "")
        if sid and sid not in seen:
            seen[sid] = s
    return list(seen.values())


async def _check_and_click_banner_windows(
    computer,
    model: str,
    capture_dir: Path,
    thread_name: str,
    settings: "ComputerSettings",
) -> None:
    """Windows path: detect banner via cropped AI vision, click the AI-returned position."""
    from workflow.run_wechat_removal import run_cropped_vision_query

    regions = get_regions(settings.os_type)
    text_output, _ = await run_cropped_vision_query(
        computer,
        model,
        banner_check_prompt(),
        capture_dir,
        f"banner_{thread_name}",
        regions.chat_content,
    )
    result = parse_banner_response(text_output)
    if result["found"] and result["x"] is not None and result["y"] is not None:
        # AI coords are 0-1000 normalised within the chat_content crop → convert to screen
        click_x, click_y = regions.chat_content.normalized_to_screen_coords(
            result["x"], result["y"]
        )
        print(f"[chat_scroll_reader] Banner detected → clicking SCREEN ({click_x}, {click_y})")
        await computer.interface.left_click(click_x, click_y)
        await asyncio.sleep(0.5)
    else:
        print("[chat_scroll_reader] No banner found, proceeding directly")


async def _check_and_click_banner_mac(
    computer,
    model: str,
    capture_dir: Path,
    thread_name: str,
    settings: "ComputerSettings",
) -> None:
    """macOS path: find the "X条新消息" banner via vision query and click it.

    WeChat Mac renders the chat window in a WKWebView/flue layer, so the AX tree
    does not expose the banner as a clickable element (same limitation as the
    three-dots / minus buttons in handle_remove).  We use a full-screenshot vision
    query — exactly the pattern used by mac_find_three_dots_prompt() etc. — and
    convert the AI-returned 0-1000 normalised coords to physical pixels for clicking
    via left_click(), which handles the Retina scale division internally.

    If the banner is not present the function returns silently; this is the normal
    case for chats that were already scrolled to the bottom.
    """
    from workflow.run_wechat_removal import run_vision_query

    text_output, _ = await run_vision_query(
        computer,
        model,
        banner_check_prompt(),
        capture_dir,
        f"banner_{thread_name}",
    )
    result = parse_banner_response(text_output)
    if not result["found"] or result["x"] is None or result["y"] is None:
        print("[chat_scroll_reader] Mac: no unread banner found, proceeding directly")
        return

    # AI coords are 0-1000 normalised within the full screenshot (physical pixels).
    # Scale to physical pixels; left_click() divides by retina scale before CGEventPost.
    click_x = round(result["x"] / 1000.0 * settings.screen_width)
    click_y = round(result["y"] / 1000.0 * settings.screen_height)
    print(f"[chat_scroll_reader] Mac banner found → clicking physical ({click_x}, {click_y})")
    await computer.interface.left_click(click_x, click_y)
    await asyncio.sleep(1.0)


async def _vision_query_for_pass(
    computer,
    model: str,
    prompt: str,
    capture_dir: Path,
    task_label: str,
    settings: "ComputerSettings",
) -> Tuple[str, List[Path]]:
    """Run a single-pass vision query, mirroring StepModeRunner._vision_query().

    Windows: crops to chat_content region to focus the model and cut token cost.
    macOS:   sends the full screenshot — same strategy used by all other Mac steps
             (classify, read_messages, handle_remove) to avoid resolution calibration.
    """
    from workflow.run_wechat_removal import run_cropped_vision_query, run_vision_query

    if settings.os_type == "macos":
        return await run_vision_query(computer, model, prompt, capture_dir, task_label)

    regions = get_regions(settings.os_type)
    return await run_cropped_vision_query(
        computer, model, prompt, capture_dir, task_label, regions.chat_content
    )


async def read_messages_with_scroll(
    computer,
    model: str,
    thread_name: str,
    thread_id: str,
    capture_dir: Path,
    settings: "ComputerSettings",
    max_passes: int = 4,
    scroll_clicks: int = 5,
) -> Tuple[List[Dict], List[Path]]:
    """
    Scroll through the chat window reading suspects on each pass.

    Returns:
        (deduplicated_suspects, all_screenshot_paths)
    """
    all_suspects: List[Dict] = []
    all_screenshots: List[Path] = []
    is_mac = settings.os_type == "macos"

    # Dismiss the unread banner so the scroll loop starts at the first unread message
    if is_mac:
        await _check_and_click_banner_mac(computer, model, capture_dir, thread_name, settings)
    else:
        await _check_and_click_banner_windows(
            computer, model, capture_dir, thread_name, settings
        )

    # Extra wait for WeChat's scroll animation from the banner click to fully settle
    # before we capture the baseline.  0.5s inside _check_and_click_banner_mac is
    # often not enough on slower machines or for longer jump animations.
    await asyncio.sleep(0.8)

    # Windows only: crop region for diff comparisons (excludes title bar / input toolbar)
    win_chat_content = None if is_mac else get_regions(settings.os_type).chat_content

    for pass_num in range(max_passes):
        print(f"[chat_scroll_reader] Pass {pass_num + 1}/{max_passes} for '{thread_name}'")

        # Capture the baseline BEFORE the vision query (which takes its own screenshot
        # internally).  This gives us a stable "current position" to diff against after
        # scrolling — taken from the same settled state the vision query will see.
        # macOS: full screenshot, no cropping.
        # Windows: crop to chat_content to ignore UI chrome outside the chat area.
        pre_pass_bytes = await computer.interface.screenshot()
        if is_mac:
            current_content = pre_pass_bytes
        else:
            current_content = _crop_bytes(pre_pass_bytes, win_chat_content)

        text_output, screenshots = await _vision_query_for_pass(
            computer,
            model,
            message_reader_prompt(thread_name, thread_id, settings.os_type),
            capture_dir,
            f"scroll_reader_{thread_id}_pass{pass_num}",
            settings,
        )
        all_screenshots.extend(screenshots)

        result = parse_reader_response(text_output, screen_height=settings.screen_height)
        if result.get("success"):
            pass_suspects = result.get("suspects", [])
            print(
                f"[chat_scroll_reader] Pass {pass_num + 1}: "
                f"{len(pass_suspects)} suspect(s) found"
            )
            all_suspects.extend(pass_suspects)

        if pass_num == max_passes - 1:
            print(f"[chat_scroll_reader] Reached max passes ({max_passes}), stopping")
            break

        await scroll_chat_window_down(computer, settings, clicks=scroll_clicks)
        await asyncio.sleep(1.0)

        after_bytes = await computer.interface.screenshot()
        if is_mac:
            after_content = after_bytes
        else:
            after_content = _crop_bytes(after_bytes, win_chat_content)

        if _at_bottom(current_content, after_content):
            print(
                f"[chat_scroll_reader] Diff identical after scroll on pass {pass_num + 1} "
                "→ reached bottom, stopping"
            )
            break

    deduped = _dedup_suspects(all_suspects)
    print(
        f"[chat_scroll_reader] Done. Total suspects after dedup: {len(deduped)} "
        f"(raw: {len(all_suspects)})"
    )
    return deduped, all_screenshots
