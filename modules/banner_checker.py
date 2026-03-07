"""
Detect and locate the WeChat unread-messages banner inside the chat window.

When a group chat is opened with unread messages, WeChat may show a clickable
banner such as "X条新消息" near the top or bottom of the message area. Clicking
it jumps to the first unread message so the scroll loop starts from the right place.

Usage:
    prompt = banner_check_prompt()
    result = parse_banner_response(text_output)
    # result: {"found": True, "x": 500, "y": 120}  ← 0-1000 normalised within screenshot
    # result: {"found": False, "x": None, "y": None}

Input:
    - text_output: JSON string from AI vision model

Output:
    - parse_banner_response: {"found": bool, "x": int | None, "y": int | None}
      x, y are normalised 0-1000 within the image sent to the model.
      On macOS the full screenshot is sent, so callers scale against screen_width/height.
      On Windows the chat_content crop is sent, so callers scale against region dimensions.
"""

from __future__ import annotations

import json


def banner_check_prompt() -> str:
    """Prompt for detecting the "X条新消息" unread-messages banner in the chat window."""
    return (
        "检查截图中是否存在微信新消息提示条（例如\"X条新消息\"或\"X条未读消息\"）。"
        "该提示条通常出现在聊天内容区域的顶部或底部附近，点击后会跳转到第一条未读消息。\n\n"
        "如果存在提示条，返回：\n"
        '{"found": true, '
        '"x": <提示条中心横坐标，0-1000归一化，0=左，1000=右>, '
        '"y": <提示条中心纵坐标，0-1000归一化，0=顶，1000=底>}\n\n'
        "如果不存在提示条，返回：\n"
        '{"found": false, "x": null, "y": null}\n\n'
        "只输出JSON，不要输出其他文字。"
    )


def parse_banner_response(text_output: str) -> dict:
    """
    Parse banner detection response from AI.

    Returns:
        {"found": bool, "x": int | None, "y": int | None}
        x, y are in normalised 0-1000 space within the image sent to the model.

    Falls back to regex extraction when the model emits malformed JSON
    (e.g. {"found": true, "x": 480, "138"} — bare value instead of "y": 138).
    """
    import re

    text = text_output.strip()
    if text.startswith("```"):
        lines = text.split("\n")[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        # Regex fallback: pull found/x/y individually from the raw text
        found_match = re.search(r'"found"\s*:\s*(true|false)', text, re.IGNORECASE)
        if not found_match or found_match.group(1).lower() != "true":
            return {"found": False, "x": None, "y": None}
        x_match = re.search(r'"x"\s*:\s*(\d+)', text)
        y_match = re.search(r'"y"\s*:\s*(\d+)', text)
        # Also catch the degenerate case {"found":true,"x":480,"138"} where y has no key
        bare_match = re.findall(r'[,{]\s*"(\d+)"', text)  # bare quoted numbers
        x = int(x_match.group(1)) if x_match else None
        y = int(y_match.group(1)) if y_match else (int(bare_match[-1]) if bare_match else None)
        return {"found": True, "x": x, "y": y}

    found = bool(payload.get("found", False))
    if not found:
        return {"found": False, "x": None, "y": None}
    x_raw = payload.get("x", None)
    y_raw = payload.get("y", None)
    x = int(x_raw) if x_raw is not None else None
    y = int(y_raw) if y_raw is not None else None
    return {"found": True, "x": x, "y": y}
