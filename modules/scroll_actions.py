"""
Scroll primitives for the WeChat chat window and left chat list panel.

Coordinate-space note for macOS
────────────────────────────────
The macOS computer-server has two separate coordinate spaces:

  • left_click(x, y)  — expects PHYSICAL pixels (matching ImageGrab.grab()).
                        Internally divides by _get_retina_scale() before posting
                        via Quartz CGEventPost, which works in logical points.

  • move_cursor(x, y) — uses pynput MouseController.position, which operates in
                        LOGICAL POINTS (half of physical on a Retina display).
                        Passing physical pixels here places the cursor 2× too far —
                        e.g. physical (1520, 920) → logical (1520, 920) → physical
                        (3040, 1840), off the right edge of a 3024-px-wide screen.

  • scroll_down(n)    — calls pynput mouse.scroll() at the CURRENT pynput cursor
                        position (logical points).  If move_cursor received wrong
                        coords the scroll fires off-screen and does nothing.

Strategy
─────────
Chat window scrolling (down / up):
  macOS   → move_cursor(centre of chat_content, LOGICAL POINTS = physical ÷ 2),
             then scroll_down(n).  Pure wheel event — no click, so WeChat's message
             view focus is not disturbed.
             NOTE: left_click uses Quartz CGEventPost and does NOT update pynput's
             internal cursor position, so scroll_down() after left_click fires at
             wherever pynput last moved — often off-screen.  Always use move_cursor
             before scroll_down on macOS.
  Windows → left_click at hard-coded screen anchor, then press("pagedown").
             Wheel fallback available via use_page_down=False.

Chat list scrolling:
  macOS   → move_cursor(centre of chat_list, LOGICAL POINTS), then scroll_down(n).
  Windows → move_cursor to hard-coded anchor, then scroll_down(n).

Usage:
    await scroll_chat_window_down(computer, settings)
    await scroll_chat_window_down(computer, settings, use_page_down=False, clicks=5)
    await scroll_chat_list_down(computer, settings, clicks=15)

Input:
    - computer:       Computer instance with interface for mouse/keyboard actions
    - settings:       ComputerSettings — os_type selects the code path; wechat_*
                      coords used only when os_type == "windows"
    - use_page_down:  If True (default), use Page Down/Up key after focusing the window.
                      If False (Windows only), fall back to mouse wheel.
    - clicks:         Wheel detents for chat-list scroll and Windows wheel fallback.
                      Default 5 for chat window, 15 for chat list.

Output:
    - Scrolls the target area by approximately one viewport.
      Includes a short sleep to allow WeChat to finish rendering.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from modules.crop_utils import get_regions

if TYPE_CHECKING:
    from runtime.computer_session import ComputerSettings

# Windows scroll anchors (SCREEN coords, 2560x1440)
_WIN_CHAT_WINDOW_X = 1288
_WIN_CHAT_WINDOW_Y = 720

_WIN_CHAT_LIST_X = 185
_WIN_CHAT_LIST_Y = 515


_MAC_RETINA_SCALE = 2  # 16" MacBook Pro: 3024×1964 physical → 1512×982 logical points


def _mac_chat_window_scroll_point(settings: "ComputerSettings"):
    """Return logical-point centre of the chat content region for pynput move_cursor.

    move_cursor() uses pynput MouseController.position, which operates in logical
    points.  On a Retina (2×) display divide physical pixels by 2.
    """
    r = get_regions(settings.os_type)
    x = (r.chat_content.x_start + r.chat_content.x_end) // 2 // _MAC_RETINA_SCALE
    y = (r.chat_content.y_start + r.chat_content.y_end) // 2 // _MAC_RETINA_SCALE
    return x, y


def _mac_chat_list_scroll_point(settings: "ComputerSettings"):
    """Return logical-point centre of the chat list sidebar for pynput move_cursor."""
    r = get_regions(settings.os_type)
    x = (r.chat_list.x_start + r.chat_list.x_end) // 2 // _MAC_RETINA_SCALE
    y = (r.chat_list.y_start + r.chat_list.y_end) // 2 // _MAC_RETINA_SCALE
    return x, y


async def scroll_chat_window_down(
    computer,
    settings: "ComputerSettings",
    use_page_down: bool = True,
    clicks: int = 5,
) -> None:
    """Scroll the chat message area down by one viewport."""
    if settings.os_type == "macos":
        # move_cursor positions pynput in logical points (physical ÷ retina scale).
        # scroll_down() then fires the wheel event at that position — no click needed,
        # so WeChat's message body focus is not disturbed.
        x, y = _mac_chat_window_scroll_point(settings)
        await computer.interface.move_cursor(x, y)
        await computer.interface.scroll_down(clicks)
    elif use_page_down:
        await computer.interface.left_click(_WIN_CHAT_WINDOW_X, _WIN_CHAT_WINDOW_Y)
        await computer.interface.press("pagedown")
    else:
        await computer.interface.move_cursor(_WIN_CHAT_WINDOW_X, _WIN_CHAT_WINDOW_Y)
        await computer.interface.scroll_down(clicks)
    await asyncio.sleep(0.3)


async def scroll_chat_window_up(
    computer,
    settings: "ComputerSettings",
    use_page_down: bool = True,
    clicks: int = 5,
) -> None:
    """Scroll the chat message area up by one viewport."""
    if settings.os_type == "macos":
        x, y = _mac_chat_window_scroll_point(settings)
        await computer.interface.move_cursor(x, y)
        await computer.interface.scroll_up(clicks)
    elif use_page_down:
        await computer.interface.left_click(_WIN_CHAT_WINDOW_X, _WIN_CHAT_WINDOW_Y)
        await computer.interface.press("pageup")
    else:
        await computer.interface.move_cursor(_WIN_CHAT_WINDOW_X, _WIN_CHAT_WINDOW_Y)
        await computer.interface.scroll_up(clicks)
    await asyncio.sleep(0.3)


async def scroll_chat_list_down(
    computer,
    settings: "ComputerSettings",
    clicks: int = 15,
) -> None:
    """Scroll the left chat list panel down by one viewport via mouse wheel."""
    if settings.os_type == "macos":
        x, y = _mac_chat_list_scroll_point(settings)
        await computer.interface.move_cursor(x, y)
    else:
        await computer.interface.move_cursor(_WIN_CHAT_LIST_X, _WIN_CHAT_LIST_Y)
    await computer.interface.scroll_down(clicks)
    await asyncio.sleep(0.5)
