"""
Detect and locate the WeChat unread-messages banner inside the chat window.

When a group chat is opened with unread messages, WeChat may show a clickable
banner such as "X条未读消息" near the top of the message area. Clicking it
jumps to the first unread message so the scroll loop starts from the right place.

Usage:
    prompt = banner_check_prompt()
    result = parse_banner_response(text_output)
    # result: {"found": True, "y": 120}  ← y in 0-1000 normalized space
    # result: {"found": False, "y": None}

Input:
    - text_output: JSON string from AI (cropped to CHAT_WINDOW_REGION)

Output:
    - parse_banner_response: {"found": bool, "y": int | None}
      y is normalized 0-1000 within CHAT_WINDOW_REGION; caller converts to screen coords.
"""

from __future__ import annotations

import json


def banner_check_prompt() -> str:
    """Prompt for detecting the unread-messages banner in the chat window."""
    return (
        "检查截图中右上角是否存在微信未读消息提示条（例如\"X条未读消息\"）。\n\n"
        "如果存在提示条，返回：\n"
        '{"found": true, "y": <提示条中心的纵坐标，0-1000归一化值，0=顶部，1000=底部>}\n\n'
        "如果不存在提示条，返回：\n"
        '{"found": false, "y": null}\n\n'
        "只输出JSON，不要输出其他文字。"
    )


def parse_banner_response(text_output: str) -> dict:
    """
    Parse banner detection response from AI.

    Returns:
        {"found": bool, "y": int | None}
        y is in normalized 0-1000 space within CHAT_WINDOW_REGION.
    """
    text = text_output.strip()
    if text.startswith("```"):
        lines = text.split("\n")[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {"found": False, "y": None}

    found = bool(payload.get("found", False))
    y_raw = payload.get("y", None)
    y = int(y_raw) if found and y_raw is not None else None
    return {"found": found, "y": y}
