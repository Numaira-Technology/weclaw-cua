"""
Fixed-position click operations for WeChat UI scaffolding.

Usage:
    await click_three_dots(computer, settings)
    await click_delete_confirm(computer, settings)

Input:
    - computer: Computer instance with interface for clicking
    - settings: ComputerSettings with wechat button positions

Output:
    - Performs click at fixed position, waits for UI response
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from runtime.computer_session import ComputerSettings


async def click_three_dots(computer, settings: "ComputerSettings") -> None:
    """Click the three dots menu button at fixed position to open group info panel."""
    x, y = settings.wechat_three_dots
    print(f"[scaffolding] Clicking three dots at ({x}, {y})")
    await computer.interface.left_click(x, y)
    await asyncio.sleep(0.5)


async def click_delete_confirm(computer, settings: "ComputerSettings") -> None:
    """Click the delete confirmation button at fixed position."""
    x, y = settings.wechat_delete_button
    print(f"[scaffolding] Clicking delete button at ({x}, {y})")
    await computer.interface.left_click(x, y)
    await asyncio.sleep(0.5)
