"""
Click correction module for detecting and compensating click position errors.

This module provides functionality to:
1. Detect cursor position from screenshots using VLM
2. Calculate offset between intended click position and actual cursor position
3. Apply accumulated offsets to future clicks for automatic correction

Usage:
    corrector = ClickCorrector(model="your-model", computer_handler=handler)

    # After a click that might have missed
    offset = await corrector.detect_and_update_offset(
        intended_x=100, intended_y=200,
        screenshot_b64=screenshot_after_click
    )

    # Apply correction to next click
    corrected_x, corrected_y = corrector.apply_correction(target_x, target_y)
"""

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ClickOffset:
    """Represents accumulated click offset for correction."""

    x_offset: float = 0.0
    y_offset: float = 0.0
    sample_count: int = 0
    confidence: float = 0.0

    def update(
        self, new_x_offset: float, new_y_offset: float, weight: float = 0.3
    ) -> None:
        """Update offset with exponential moving average."""
        if self.sample_count == 0:
            self.x_offset = new_x_offset
            self.y_offset = new_y_offset
            self.confidence = 0.5
        else:
            self.x_offset = (1 - weight) * self.x_offset + weight * new_x_offset
            self.y_offset = (1 - weight) * self.y_offset + weight * new_y_offset
            self.confidence = min(1.0, self.confidence + 0.1)
        self.sample_count += 1

    def reset(self) -> None:
        """Reset offset to zero."""
        self.x_offset = 0.0
        self.y_offset = 0.0
        self.sample_count = 0
        self.confidence = 0.0


@dataclass
class ClickCorrectionConfig:
    """Configuration for click correction behavior."""

    enabled: bool = True
    max_offset: int = 100
    min_samples_for_correction: int = 1
    auto_detect_on_failure: bool = True
    detection_threshold: float = 10.0


class ClickCorrector:
    """Handles click position correction through cursor detection and offset tracking."""

    def __init__(
        self,
        model: str = "openrouter/qwen/qwen-2.5-vl-72b-instruct",
        config: Optional[ClickCorrectionConfig] = None,
    ):
        self.model = model
        self.config = config or ClickCorrectionConfig()
        self.offset = ClickOffset()
        self._last_intended_click: Optional[Tuple[int, int]] = None
        self._detection_history: List[Dict[str, Any]] = []

    def record_intended_click(self, x: int, y: int) -> None:
        """Record the intended click position before executing click."""
        self._last_intended_click = (x, y)

    def apply_correction(self, x: int, y: int) -> Tuple[int, int]:
        """Apply accumulated offset correction to target coordinates."""
        if not self.config.enabled:
            return x, y

        if self.offset.sample_count < self.config.min_samples_for_correction:
            return x, y

        corrected_x = int(round(x + self.offset.x_offset))
        corrected_y = int(round(y + self.offset.y_offset))

        return corrected_x, corrected_y

    async def detect_cursor_position(
        self,
        screenshot_b64: str,
        hint_x: Optional[int] = None,
        hint_y: Optional[int] = None,
    ) -> Optional[Tuple[int, int]]:
        """Detect cursor position from screenshot using VLM.

        Args:
            screenshot_b64: Base64 encoded screenshot
            hint_x: Optional hint for expected x position
            hint_y: Optional hint for expected y position

        Returns:
            Tuple of (x, y) cursor position, or None if detection failed
        """
        import litellm

        hint_text = ""
        if hint_x is not None and hint_y is not None:
            hint_text = f" The cursor should be near position ({hint_x}, {hint_y})."

        prompt = f"""Look at this screenshot and find the mouse cursor position.
The cursor appears as an arrow pointer on screen.{hint_text}

Return ONLY a JSON object with the cursor coordinates in this exact format:
{{"cursor_x": <number>, "cursor_y": <number>}}

If you cannot find the cursor, return:
{{"cursor_x": null, "cursor_y": null}}"""

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"},
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ]

        try:
            response = await litellm.acompletion(
                model=self.model,
                messages=messages,
                max_tokens=100,
                temperature=0.1,
            )

            content = response.choices[0].message.content or ""

            json_match = re.search(r"\{[^}]+\}", content)
            if json_match:
                data = json.loads(json_match.group())
                cursor_x = data.get("cursor_x")
                cursor_y = data.get("cursor_y")

                if cursor_x is not None and cursor_y is not None:
                    return (int(cursor_x), int(cursor_y))

            return None

        except Exception as e:
            print(f"Cursor detection failed: {e}")
            return None

    async def detect_and_update_offset(
        self,
        intended_x: int,
        intended_y: int,
        screenshot_b64: str,
    ) -> Optional[Tuple[float, float]]:
        """Detect cursor position and update offset based on difference from intended position.

        Args:
            intended_x: The x coordinate where we intended to click
            intended_y: The y coordinate where we intended to click
            screenshot_b64: Screenshot taken after the click

        Returns:
            Tuple of (x_offset, y_offset) if detection successful, None otherwise
        """
        cursor_pos = await self.detect_cursor_position(
            screenshot_b64, hint_x=intended_x, hint_y=intended_y
        )

        if cursor_pos is None:
            return None

        actual_x, actual_y = cursor_pos

        x_diff = intended_x - actual_x
        y_diff = intended_y - actual_y

        distance = (x_diff**2 + y_diff**2) ** 0.5

        self._detection_history.append(
            {
                "intended": (intended_x, intended_y),
                "actual": (actual_x, actual_y),
                "diff": (x_diff, y_diff),
                "distance": distance,
            }
        )

        if len(self._detection_history) > 20:
            self._detection_history = self._detection_history[-20:]

        if distance > self.config.detection_threshold:
            if (
                abs(x_diff) <= self.config.max_offset
                and abs(y_diff) <= self.config.max_offset
            ):
                self.offset.update(x_diff, y_diff)
                return (x_diff, y_diff)

        return (0.0, 0.0)

    async def analyze_click_failure(
        self,
        intended_x: int,
        intended_y: int,
        screenshot_before: str,
        screenshot_after: str,
        target_description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Analyze why a click might have failed by comparing before/after screenshots.

        Args:
            intended_x: Where we tried to click
            intended_y: Where we tried to click
            screenshot_before: Screenshot before the click
            screenshot_after: Screenshot after the click
            target_description: Optional description of what we were trying to click

        Returns:
            Analysis result with suggested correction
        """
        import litellm

        target_text = f" on '{target_description}'" if target_description else ""

        prompt = f"""I attempted to click at position ({intended_x}, {intended_y}){target_text}.

Compare these two screenshots (before and after the click) and analyze:
1. Where is the cursor in the AFTER screenshot?
2. Did the click hit the intended target?
3. If not, how far off was the click?

Return a JSON object:
{{
    "cursor_position": {{"x": <number>, "y": <number>}},
    "click_hit_target": <true/false>,
    "offset_x": <number>,  // positive = cursor is right of intended, need to click more left
    "offset_y": <number>,  // positive = cursor is below intended, need to click more up
    "analysis": "<brief explanation>"
}}"""

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "BEFORE click:"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{screenshot_before}"
                        },
                    },
                    {"type": "text", "text": "AFTER click:"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{screenshot_after}"
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ]

        try:
            response = await litellm.acompletion(
                model=self.model,
                messages=messages,
                max_tokens=300,
                temperature=0.1,
            )

            content = response.choices[0].message.content or ""

            json_match = re.search(r"\{[^}]*\}", content, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())

                if not result.get("click_hit_target", True):
                    offset_x = result.get("offset_x", 0)
                    offset_y = result.get("offset_y", 0)

                    if (
                        abs(offset_x) <= self.config.max_offset
                        and abs(offset_y) <= self.config.max_offset
                    ):
                        self.offset.update(-offset_x, -offset_y)

                return result

            return {"error": "Failed to parse analysis", "raw": content}

        except Exception as e:
            return {"error": str(e)}

    def get_correction_stats(self) -> Dict[str, Any]:
        """Get statistics about click correction."""
        return {
            "current_offset": {
                "x": self.offset.x_offset,
                "y": self.offset.y_offset,
            },
            "sample_count": self.offset.sample_count,
            "confidence": self.offset.confidence,
            "recent_detections": (
                self._detection_history[-5:] if self._detection_history else []
            ),
        }

    def reset(self) -> None:
        """Reset all correction state."""
        self.offset.reset()
        self._last_intended_click = None
        self._detection_history.clear()


class ClickCorrectionCallback:
    """Callback that integrates click correction into the agent loop."""

    def __init__(self, corrector: ClickCorrector):
        self.corrector = corrector
        self._pending_click: Optional[Dict[str, Any]] = None
        self._screenshot_before: Optional[str] = None

    async def on_computer_call_start(self, item: Dict[str, Any]) -> None:
        """Called before a computer action is executed."""
        action = item.get("action", {})
        action_type = action.get("type", "")

        if action_type in ("click", "left_click", "double_click"):
            x = action.get("x")
            y = action.get("y")
            if x is not None and y is not None:
                self._pending_click = {"x": x, "y": y, "type": action_type}
                self.corrector.record_intended_click(x, y)

    async def on_screenshot(self, screenshot: str, name: str = "screenshot") -> None:
        """Called when a screenshot is taken."""
        if name == "screenshot_before":
            self._screenshot_before = screenshot
        elif name == "screenshot_after" and self._pending_click:
            await self.corrector.detect_and_update_offset(
                self._pending_click["x"],
                self._pending_click["y"],
                screenshot,
            )
            self._pending_click = None
