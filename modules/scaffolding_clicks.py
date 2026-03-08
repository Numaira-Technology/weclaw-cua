"""
Click operations for WeChat UI — dispatches by OS.

On Windows: uses hard-coded SCREEN COORDINATES from ComputerSettings (original
behaviour, unchanged).

On macOS: uses the AX accessibility tree (ax_clicks.py) — no fixed coords,
no image crops.  The settings argument is accepted for API compatibility but
the wechat_* position fields are not used.

Reference positions for Windows (SCREEN coords, 2560x1440):
- Three dots button: (2525, 48)
- Minus button:      (2525, 200)
- Delete/移出 button: (1345, 920)

Usage:
    await click_three_dots(computer, settings)
    await click_minus_button(computer, settings)
    await click_delete_confirm(computer, settings)

Input:
    - computer:  Computer instance with interface for clicking / AX tree
    - settings:  ComputerSettings — os_type selects the implementation path;
                 wechat_* coords used only when os_type == "windows"

Output:
    - Performs the click and waits for UI response
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from runtime.computer_session import ComputerSettings


async def click_three_dots(computer, settings: "ComputerSettings") -> None:
    """Click the three-dots / group-info button."""
    if settings.os_type == "macos":
        from modules.ax_clicks import ax_click_three_dots
        await ax_click_three_dots(computer)
    else:
        x, y = settings.wechat_three_dots
        print(f"[scaffolding] Clicking three dots at SCREEN ({x}, {y})")
        await computer.interface.left_click(x, y)
        await asyncio.sleep(0.5)


async def click_minus_button(computer, settings: "ComputerSettings") -> None:
    """Click the minus / remove-member button."""
    if settings.os_type == "macos":
        from modules.ax_clicks import ax_click_minus_button
        await ax_click_minus_button(computer)
    else:
        x, y = settings.wechat_minus_button
        print(f"[scaffolding] Clicking minus button at SCREEN ({x}, {y})")
        await computer.interface.left_click(x, y)
        await asyncio.sleep(0.5)


async def click_delete_confirm(computer, settings: "ComputerSettings") -> None:
    """Click the delete/移出 confirmation button."""
    if settings.os_type == "macos":
        from modules.ax_clicks import ax_click_delete_confirm
        await ax_click_delete_confirm(computer)
    else:
        x, y = settings.wechat_delete_button
        print(f"[scaffolding] Clicking delete button at SCREEN ({x}, {y})")
        await computer.interface.left_click(x, y)
        await asyncio.sleep(0.5)
