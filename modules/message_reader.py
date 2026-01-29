"""
Read unread messages inside a specific group thread and surface suspects.

Usage:
    prompt = message_reader_prompt(thread_name, thread_id)
    result = parse_reader_response(text_output)

Input:
    - thread_name: Name of the group chat to verify
    - thread_id: ID of the thread for JSON output
    - text_output: JSON response from the AI

Output:
    - message_reader_prompt: Prompt for verification + reading in single API call
    - parse_reader_response: Parsed result with success flag and suspects/retry_y
"""

from __future__ import annotations

import json
from typing import Any, Dict


def message_reader_prompt(thread_name: str, thread_id: str) -> str:
    """Generate prompt for verifying chat is open and reading messages."""
    return (
        f"任务：验证并读取群聊「{thread_name}」的消息。\n\n"
        "第一步：验证\n"
        f"检查右侧聊天区域是否显示群聊「{thread_name}」的消息内容。\n"
        "- 查看聊天窗口顶部的群名是否匹配\n"
        "- 确认消息内容区域可见\n\n"
        "第二步：根据验证结果返回JSON\n\n"
        "如果验证成功（正确的群聊已打开）：\n"
        "- 查找包含「代写」的消息\n"
        "- 返回JSON格式：\n"
        f'{{"success": true, "thread_id": "{thread_id}", "suspects": [{{"sender_id": "xxx", "sender_name": "xxx", "evidence_text": "xxx"}}]}}\n'
        "- 如果没有可疑消息，suspects为空数组：\n"
        f'{{"success": true, "thread_id": "{thread_id}", "suspects": []}}\n\n'
        "如果验证失败（错误的聊天或聊天未打开）：\n"
        f"- 在左侧聊天列表中找到「{thread_name}」\n"
        "- 估算该会话头像中心的Y坐标（0-1000归一化值，0=顶部，1000=底部）\n"
        "- 提示：第一个会话约在y=97，每个会话间隔约35\n"
        "- 返回JSON格式：\n"
        '{"success": false, "retry_y": 97}\n\n'
        "只输出JSON，不要输出其他文字。"
    )


def parse_reader_response(
    text_output: str, screen_height: int = 1440
) -> Dict[str, Any]:
    """
    Parse reader response, handling both success and retry cases.
    Converts normalized retry_y (0-1000) to pixel coordinates.

    Args:
        text_output: JSON string from AI with retry_y in 0-1000 normalized space
        screen_height: Screen height in pixels for conversion (default 1440)

    Returns:
        - On success: {"success": True, "thread_id": str, "suspects": [...]}
        - On retry: {"success": False, "retry_y": int} (in pixel coordinates)
    """
    text = text_output.strip()

    # Handle markdown code blocks
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]  # Remove opening ```json or ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]  # Remove closing ```
        text = "\n".join(lines)

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        # If parsing fails, return retry with y=0 to trigger re-attempt
        return {"success": False, "retry_y": 0, "error": "json_parse_failed"}

    success = payload.get("success", False)

    if success:
        return {
            "success": True,
            "thread_id": payload.get("thread_id", ""),
            "suspects": payload.get("suspects", []),
        }
    else:
        # Convert from 0-1000 normalized space to pixel space
        normalized_y = payload.get("retry_y", 0)
        pixel_y = int((normalized_y / 1000.0) * screen_height)
        return {
            "success": False,
            "retry_y": pixel_y,
        }
