"""
Fixed-position click operations for WeChat UI scaffolding.

All click positions are in SCREEN COORDINATES (absolute pixels on 2560x1440).
These values come from ComputerSettings which loads from config/computer_windows.yaml.

Reference positions (SCREEN coords):
- Three dots button: (2525, 48)
- Minus button: (2525, 200)
- Delete/移出 button: (1345, 920)

Usage:
    await click_three_dots(computer, settings)
    await click_minus_button(computer, settings)
    await click_delete_confirm(computer, settings)

Input:
    - computer: Computer instance with interface for clicking
    - settings: ComputerSettings with wechat button positions (SCREEN coords)

Output:
    - Performs click at fixed position, waits for UI response
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from runtime.computer_session import ComputerSettings


async def click_three_dots(computer, settings: "ComputerSettings") -> None:
    """Click the three dots menu button at fixed position to open group info panel.

    Position: SCREEN coords from settings (default: 2525, 48)
    """
    x, y = settings.wechat_three_dots  # SCREEN coordinates
    print(f"[scaffolding] Clicking three dots at SCREEN ({x}, {y})")
    await computer.interface.left_c"""  """lick(x, y)
    await asyncio.sleep(0.5)


async def click_minus_button(computer, settings: "ComputerSettings") -> None:
    """Click the minus button at fixed position to enter member removal mode.

    Position: SCREEN coords from settings (default: 2525, 200)
    """
    x, y = settings.wechat_minus_button  # SCREEN coordinates
    print(f"[scaffolding] Clicking minus button at SCREEN ({x}, {y})")
    await computer.interface.left_click(x, y)
    await asyncio.sleep(0.5)


async def click_delete_confirm(computer, settings: "ComputerSettings") -> None:
    """Click the delete/移出 confirmation button at fixed position.

    Position: SCREEN coords from settings (default: 1345, 920)
    """
    x, y = settings.wechat_delete_button  # SCREEN coordinates
    print(f"[scaffolding] Clicking delete button at SCREEN ({x}, {y})")
    await computer.interface.left_click(x, y)
    await asyncio.sleep(0.5)
