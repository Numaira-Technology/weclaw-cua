"""
Multi-pass scroll reader for the WeChat chat window (step 5).

Reads all unread messages by scrolling down until no new content appears,
using PIL screenshot diff to detect when the bottom has been reached.

Usage:
    suspects, screenshots = await read_messages_with_scroll(
        computer, model, thread_name, thread_id,
        capture_dir, max_passes=4, scroll_clicks=5
    )

Input:
    - computer: Computer instance (connected)
    - model: LiteLLM model string
    - thread_name: Display name of the group chat (used for capture filenames)
    - thread_id: Unique ID of the thread
    - capture_dir: Path where screenshots are saved
    - max_passes: Hard cap on scroll iterations (default 4)
    - scroll_clicks: Scroll notches per pass (only used when use_page_down=False)

Output:
    - suspects: List of dicts [{sender_id, sender_name, evidence_text}], deduplicated
    - screenshots: All screenshot Paths captured during the loop
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Dict, List, Tuple

from PIL import Image, ImageChops

from modules.banner_checker import banner_check_prompt, parse_banner_response
from modules.crop_utils import CHAT_CONTENT_REGION
from modules.message_reader import message_reader_prompt, parse_reader_response
from modules.scroll_actions import scroll_chat_window_down


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


async def _check_and_click_banner(
    computer,
    model: str,
    capture_dir: Path,
    thread_name: str,
    settings,
) -> None:
    """Detect unread banner via AI; if present, click the hardcoded screen position."""
    from workflow.run_wechat_removal import run_cropped_vision_query

    text_output, _ = await run_cropped_vision_query(
        computer,
        model,
        banner_check_prompt(),
        capture_dir,
        f"banner_{thread_name}",
        CHAT_CONTENT_REGION,
    )
    result = parse_banner_response(text_output)
    if result["found"]:
        x, y = settings.wechat_banner
        print(f"[chat_scroll_reader] Banner detected → clicking hardcoded SCREEN ({x}, {y})")
        await computer.interface.left_click(x, y)
        import asyncio
        await asyncio.sleep(0.5)
    else:
        print("[chat_scroll_reader] No banner found, proceeding directly")


async def read_messages_with_scroll(
    computer,
    model: str,
    thread_name: str,
    thread_id: str,
    capture_dir: Path,
    settings,
    max_passes: int = 4,
    scroll_clicks: int = 5,
) -> Tuple[List[Dict], List[Path]]:
    """
    Scroll through the chat window, reading suspects on each pass.

    Returns:
        (deduplicated_suspects, all_screenshot_paths)
    """
    import asyncio
    from workflow.run_wechat_removal import run_vision_query

    all_suspects: List[Dict] = []
    all_screenshots: List[Path] = []

    await _check_and_click_banner(computer, model, capture_dir, thread_name, settings)

    # Current frame: state after banner click (or initial state if no banner)
    post_banner_bytes = await computer.interface.screenshot()
    current_content = _crop_bytes(post_banner_bytes, CHAT_CONTENT_REGION)

    for pass_num in range(max_passes):
        print(f"[chat_scroll_reader] Pass {pass_num + 1}/{max_passes} for '{thread_name}'")

        # Read current viewport
        text_output, screenshots = await run_vision_query(
            computer,
            model,
            message_reader_prompt(thread_name, thread_id),
            capture_dir,
            f"scroll_reader_{thread_id}_pass{pass_num}",
        )
        all_screenshots.extend(screenshots)

        result = parse_reader_response(text_output)
        if result.get("success"):
            pass_suspects = result.get("suspects", [])
            print(
                f"[chat_scroll_reader] Pass {pass_num + 1}: "
                f"{len(pass_suspects)} suspect(s) found"
            )
            all_suspects.extend(pass_suspects)

        # On the last allowed pass, stop without scrolling to avoid a hanging
        # computer-server call that would block indefinitely with no benefit.
        if pass_num == max_passes - 1:
            print(
                f"[chat_scroll_reader] Reached max passes ({max_passes}), stopping"
            )
            break

        # Scroll and immediately capture the result
        await scroll_chat_window_down(computer, clicks=scroll_clicks)
        await asyncio.sleep(0.2)

        after_bytes = await computer.interface.screenshot()
        after_content = _crop_bytes(after_bytes, CHAT_CONTENT_REGION)

        if _at_bottom(current_content, after_content):
            print(
                f"[chat_scroll_reader] Diff identical after scroll on pass {pass_num + 1} "
                "→ reached bottom, stopping"
            )
            break

        # After-scroll frame becomes the baseline for the next pass
        current_content = after_content

    deduped = _dedup_suspects(all_suspects)
    print(
        f"[chat_scroll_reader] Done. Total suspects after dedup: {len(deduped)} "
        f"(raw: {len(all_suspects)})"
    )
    return deduped, all_screenshots
