"""
Computer handler implementation for OpenAI computer-use-preview protocol.
"""

import base64
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

from computer import Computer

from ..click_correction import ClickCorrector
from .base import AsyncComputerHandler


class cuaComputerHandler(AsyncComputerHandler):
    """Computer handler that implements the Computer protocol using the computer interface."""

    def __init__(
        self,
        cua_computer: Computer,
        enable_click_correction: bool = False,
        click_correction_model: Optional[str] = None,
    ):
        """Initialize with a computer interface (from tool schema).

        Args:
            cua_computer: The computer interface
            enable_click_correction: Whether to enable automatic click correction
            click_correction_model: Model to use for cursor detection (default: same as agent)
        """
        self.cua_computer = cua_computer
        self.interface = None

        # Click correction
        self._click_correction_enabled = enable_click_correction
        self._click_corrector: Optional[ClickCorrector] = None
        self._click_correction_model = click_correction_model
        self._last_click_coords: Optional[Tuple[int, int]] = None

    async def _initialize(self):
        if (
            hasattr(self.cua_computer, "_initialized")
            and not self.cua_computer._initialized
        ):
            await self.cua_computer.run()
        self.interface = self.cua_computer.interface

        # Initialize click corrector if enabled
        if self._click_correction_enabled and self._click_corrector is None:
            model = (
                self._click_correction_model
                or "openrouter/qwen/qwen-2.5-vl-72b-instruct"
            )
            self._click_corrector = ClickCorrector(model=model)

    def enable_click_correction(self, model: Optional[str] = None) -> None:
        """Enable click correction with optional model override."""
        self._click_correction_enabled = True
        if model:
            self._click_correction_model = model
        if self._click_corrector is None:
            self._click_corrector = ClickCorrector(
                model=model or "openrouter/qwen/qwen-2.5-vl-72b-instruct"
            )

    def disable_click_correction(self) -> None:
        """Disable click correction."""
        self._click_correction_enabled = False

    def get_click_correction_stats(self) -> Optional[Dict[str, Any]]:
        """Get current click correction statistics."""
        if self._click_corrector:
            return self._click_corrector.get_correction_stats()
        return None

    def reset_click_correction(self) -> None:
        """Reset click correction offset to zero."""
        if self._click_corrector:
            self._click_corrector.reset()

    # ==== Computer-Use-Preview Action Space ====

    async def get_environment(self) -> Literal["windows", "mac", "linux", "browser"]:
        """Get the current environment type."""
        # TODO: detect actual environment
        return "linux"

    async def get_dimensions(self) -> tuple[int, int]:
        """Get screen dimensions as (width, height)."""
        assert self.interface is not None
        screen_size = await self.interface.get_screen_size()
        return screen_size["width"], screen_size["height"]

    async def screenshot(self, text: Optional[str] = None) -> str:
        """Take a screenshot and return as base64 string.

        Args:
            text: Optional descriptive text (for compatibility with GPT-4o models, ignored)
        """
        assert self.interface is not None
        screenshot_bytes = await self.interface.screenshot()
        return base64.b64encode(screenshot_bytes).decode("utf-8")

    async def update_click_correction(
        self, screenshot_b64: str
    ) -> Optional[Tuple[float, float]]:
        """Update click correction based on cursor position in screenshot.

        Call this after a click to detect if the click was off-target and
        update the correction offset.

        Args:
            screenshot_b64: Base64 encoded screenshot taken after the click

        Returns:
            Tuple of (x_offset, y_offset) if correction was updated, None otherwise
        """
        if not self._click_correction_enabled or not self._click_corrector:
            return None

        if self._last_click_coords is None:
            return None

        intended_x, intended_y = self._last_click_coords
        result = await self._click_corrector.detect_and_update_offset(
            intended_x, intended_y, screenshot_b64
        )

        return result

    async def analyze_click_failure(
        self,
        screenshot_before: str,
        screenshot_after: str,
        target_description: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Analyze a click failure by comparing before/after screenshots.

        Use this when a click didn't produce the expected result.

        Args:
            screenshot_before: Screenshot taken before the click
            screenshot_after: Screenshot taken after the click
            target_description: Description of what was being clicked

        Returns:
            Analysis result with suggested correction, or None if correction disabled
        """
        if not self._click_corrector:
            return None

        if self._last_click_coords is None:
            return {"error": "No recent click recorded"}

        intended_x, intended_y = self._last_click_coords
        return await self._click_corrector.analyze_click_failure(
            intended_x,
            intended_y,
            screenshot_before,
            screenshot_after,
            target_description,
        )

    async def get_cursor_position_from_screenshot(
        self, screenshot_b64: str
    ) -> Optional[Tuple[int, int]]:
        """Detect cursor position from a screenshot using VLM.

        Args:
            screenshot_b64: Base64 encoded screenshot

        Returns:
            Tuple of (x, y) cursor position, or None if detection failed
        """
        if not self._click_corrector:
            # Create temporary corrector for detection
            corrector = ClickCorrector()
            return await corrector.detect_cursor_position(screenshot_b64)

        return await self._click_corrector.detect_cursor_position(screenshot_b64)

    async def click(self, x: int, y: int, button: str = "left") -> None:
        """Click at coordinates with specified button.

        Coordinates are expected to be in screenshot space (from model output).
        They are converted to screen space before clicking.
        If click correction is enabled, applies accumulated offset.
        """
        assert self.interface is not None

        # Apply click correction if enabled
        if self._click_correction_enabled and self._click_corrector:
            x, y = self._click_corrector.apply_correction(x, y)

        # Convert from screenshot coordinates to screen coordinates
        # The model outputs coordinates based on the screenshot it sees,
        # but clicks need to happen in actual screen space
        screen_x, screen_y = await self.interface.to_screen_coordinates(
            float(x), float(y)
        )
        screen_x, screen_y = int(round(screen_x)), int(round(screen_y))

        # Record for click correction
        self._last_click_coords = (x, y)
        if self._click_corrector:
            self._click_corrector.record_intended_click(x, y)

        if button == "left":
            await self.interface.left_click(screen_x, screen_y)
        elif button == "right":
            await self.interface.right_click(screen_x, screen_y)
        else:
            # Default to left click for unknown buttons
            await self.interface.left_click(screen_x, screen_y)

    async def double_click(self, x: int, y: int) -> None:
        """Double click at coordinates (in screenshot space, converted to screen space)."""
        assert self.interface is not None
        # Convert from screenshot coordinates to screen coordinates
        screen_x, screen_y = await self.interface.to_screen_coordinates(
            float(x), float(y)
        )
        screen_x, screen_y = int(round(screen_x)), int(round(screen_y))
        await self.interface.double_click(screen_x, screen_y)

    async def scroll(self, x: int, y: int, scroll_x: int, scroll_y: int) -> None:
        """Scroll at coordinates with specified scroll amounts (coordinates in screenshot space)."""
        assert self.interface is not None
        # Convert from screenshot coordinates to screen coordinates
        screen_x, screen_y = await self.interface.to_screen_coordinates(
            float(x), float(y)
        )
        screen_x, screen_y = int(round(screen_x)), int(round(screen_y))
        await self.interface.move_cursor(screen_x, screen_y)
        await self.interface.scroll(scroll_x, scroll_y)

    async def type(self, text: str) -> None:
        """Type text."""
        assert self.interface is not None
        await self.interface.type_text(text)

    async def wait(self, ms: int = 1000) -> None:
        """Wait for specified milliseconds."""
        assert self.interface is not None
        import asyncio

        await asyncio.sleep(ms / 1000.0)

    async def move(self, x: int, y: int) -> None:
        """Move cursor to coordinates (in screenshot space, converted to screen space)."""
        assert self.interface is not None
        # Convert from screenshot coordinates to screen coordinates
        screen_x, screen_y = await self.interface.to_screen_coordinates(
            float(x), float(y)
        )
        screen_x, screen_y = int(round(screen_x)), int(round(screen_y))
        await self.interface.move_cursor(screen_x, screen_y)

    async def keypress(self, keys: Union[List[str], str]) -> None:
        """Press key combination."""
        assert self.interface is not None
        if isinstance(keys, str):
            keys = keys.replace("-", "+").split("+")
        if len(keys) == 1:
            await self.interface.press_key(keys[0])
        else:
            # Handle key combinations
            await self.interface.hotkey(*keys)

    async def drag(self, path: List[Dict[str, int]]) -> None:
        """Drag along specified path (coordinates in screenshot space)."""
        assert self.interface is not None
        if not path:
            return

        # Convert all path points from screenshot to screen coordinates
        screen_path = []
        for point in path:
            screen_x, screen_y = await self.interface.to_screen_coordinates(
                float(point["x"]), float(point["y"])
            )
            screen_path.append({"x": int(round(screen_x)), "y": int(round(screen_y))})

        # Start drag from first point
        start = screen_path[0]
        await self.interface.mouse_down(start["x"], start["y"])

        # Move through path
        for point in screen_path[1:]:
            await self.interface.move_cursor(point["x"], point["y"])

        # End drag at last point
        end = screen_path[-1]
        await self.interface.mouse_up(end["x"], end["y"])

    async def get_current_url(self) -> str:
        """Get current URL (for browser environments)."""
        # This would need to be implemented based on the specific browser interface
        # For now, return empty string
        return ""

    # ==== Anthropic Computer Action Space ====
    async def left_mouse_down(
        self, x: Optional[int] = None, y: Optional[int] = None
    ) -> None:
        """Left mouse down at coordinates."""
        assert self.interface is not None
        await self.interface.mouse_down(x, y, button="left")

    async def left_mouse_up(
        self, x: Optional[int] = None, y: Optional[int] = None
    ) -> None:
        """Left mouse up at coordinates."""
        assert self.interface is not None
        await self.interface.mouse_up(x, y, button="left")

    # ==== Browser Control Methods (via Playwright) ====
    async def playwright_exec(
        self, command: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute a Playwright browser command.

        Supports: visit_url, click, type, scroll, web_search, screenshot,
                  get_current_url, go_back, go_forward

        Args:
            command: The browser command to execute
            params: Command parameters

        Returns:
            Dict containing the command result
        """
        assert self.interface is not None
        return await self.interface.playwright_exec(command, params or {})
