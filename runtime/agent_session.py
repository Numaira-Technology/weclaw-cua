"""
Maintains conversation history across multiple prompts within one logical session.

Usage:
    session = AgentSession(agent)
    response1, screenshots1 = await session.run(prompt1, capture_dir, "task1")
    response2, screenshots2 = await session.run(prompt2, capture_dir, "task2")
    # Both prompts share the same conversation context

Input:
    - agent: ComputerAgent instance
    - prompt: User prompt string
    - capture_dir: Path to save screenshots
    - label: Task label for screenshot naming

Output:
    - Tuple of (response_text, screenshot_paths)
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _sanitize_surrogates(text: str) -> str:
    """Remove surrogate characters that cause UTF-8 encoding errors."""
    return text.encode("utf-8", errors="surrogatepass").decode(
        "utf-8", errors="replace"
    )


def _save_screenshot(image_url: str, path: Path) -> None:
    """Save base64 image URL to file."""
    assert image_url.startswith("data:image"), f"Invalid image URL: {image_url[:50]}"
    _, encoded = image_url.split(",", 1)
    data = base64.b64decode(encoded)
    path.write_bytes(data)


@dataclass
class AgentSession:
    """Maintains conversation history across multiple prompts within one logical session."""

    agent: Any
    messages: List[Dict[str, Any]] = field(default_factory=list)

    async def run(
        self, prompt: str, capture_dir: Path, label: str
    ) -> Tuple[str, List[Path]]:
        """
        Run prompt within session, accumulating full conversation history.

        Each call appends the new prompt and agent responses to the shared
        message history, enabling multi-turn conversations with context.
        """
        self.messages.append({"role": "user", "content": prompt})

        text_messages: List[str] = []
        screenshot_paths: List[Path] = []
        screenshot_index = 0

        async for result in self.agent.run(self.messages):
            for item in result["output"]:
                self.messages.append(item)

                item_type = item.get("type")
                if item_type == "message":
                    for content_item in item.get("content", []):
                        text = content_item.get("text")
                        if text:
                            text_messages.append(_sanitize_surrogates(text))

                elif item_type == "computer_call_output":
                    output = item.get("output", {})
                    image_url = output.get("image_url", "")
                    if image_url:
                        path = capture_dir / f"{label}_{screenshot_index}.png"
                        _save_screenshot(image_url, path)
                        screenshot_paths.append(path)
                        screenshot_index += 1

        final_text = text_messages[-1] if text_messages else ""
        return final_text, screenshot_paths

    def clear(self) -> None:
        """Clear conversation history to start fresh."""
        self.messages.clear()
