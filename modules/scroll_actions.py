"""
Scroll primitives for the WeChat chat window and left chat list panel.

Usage:
    await scroll_chat_window_down(computer)       # one full viewport via Page Down
    await scroll_chat_window_down(computer, use_page_down=False, clicks=5)  # wheel fallback
    await scroll_chat_list_down(computer, clicks=15)  # left panel, one viewport via wheel

Input:
    - computer: Computer instance with interface for mouse/keyboard actions
    - use_page_down: If True (default), press Page Down for a reliable full-viewport scroll.
                     If False, fall back to mouse wheel with `clicks` detents.
    - clicks: Wheel detents (default 5 for chat window, 15 for chat list).
              Note: 1 detent ≈ 3 lines at default Windows scroll speed — not a fixed pixel count.

Output:
    - Scrolls the target area down/up by approximately one viewport.
      Includes a short sleep to allow WeChat to finish rendering.
"""

from __future__ import annotations

import asyncio

# Scroll anchor: center of chat window — cursor must be inside the area before wheel scroll
_CHAT_WINDOW_SCROLL_X = 1288
_CHAT_WINDOW_SCROLL_Y = 720

# Scroll anchor: center of left chat list panel (CHAT_LIST_REGION x=60-310, y=0-1030)
_CHAT_LIST_SCROLL_X = 185
_CHAT_LIST_SCROLL_Y = 515


async def scroll_chat_window_down(
    computer, use_page_down: bool = True, clicks: int = 5
) -> None:
    """Scroll the chat message area down by one viewport (Page Down) or by wheel clicks."""
    if use_page_down:
        await computer.interface.left_click(_CHAT_WINDOW_SCROLL_X, _CHAT_WINDOW_SCROLL_Y)
        await computer.interface.press("pagedown")
    else:
        await computer.interface.move_cursor(_CHAT_WINDOW_SCROLL_X, _CHAT_WINDOW_SCROLL_Y)
        await computer.interface.scroll_down(clicks)
    await asyncio.sleep(0.3)


async def scroll_chat_list_down(computer, clicks: int = 15) -> None:
    """Scroll the left chat list panel down by one viewport via mouse wheel."""
    await computer.interface.move_cursor(_CHAT_LIST_SCROLL_X, _CHAT_LIST_SCROLL_Y)
    await computer.interface.scroll_down(clicks)
    await asyncio.sleep(0.5)


async def scroll_chat_window_up(
    computer, use_page_down: bool = True, clicks: int = 5
) -> None:
    """Scroll the chat message area up by one viewport (Page Up) or by wheel clicks."""
    if use_page_down:
        await computer.interface.left_click(_CHAT_WINDOW_SCROLL_X, _CHAT_WINDOW_SCROLL_Y)
        await computer.interface.press("pageup")
    else:
        await computer.interface.move_cursor(_CHAT_WINDOW_SCROLL_X, _CHAT_WINDOW_SCROLL_Y)
        await computer.interface.scroll_up(clicks)
    await asyncio.sleep(0.3)
