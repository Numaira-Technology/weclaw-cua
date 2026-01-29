"""
Classify WeChat threads as group or individual using icon cues.

Usage:
  prompt = classification_prompt()
  threads = parse_classification(text_output)

Input:
  - text_output: JSON string returned by the agent with thread_id, name, is_group, unread.

Output:
  - classification_prompt: string sent to the agent to run the classification step.
  - List[GroupThread]: parsed classification results.
"""

from __future__ import annotations

import json
from typing import List

from modules.task_types import GroupThread


def classification_prompt() -> str:
    return (
        "这是微信会话列表的裁剪截图（宽218像素，高1440像素，仅显示左侧聊天列表栏）。"
        "分析截图中可见的每个会话，从上到下依次列出。"
        "使用头像图标区分群聊（多人头像/九宫格）与单聊（单人头像）。"
        "记录每个会话的未读状态（是否有红色未读消息标记）。"
        "对于每个会话，估算其头像中心点的Y坐标（0-1000归一化值，0=顶部，1000=底部）。"
        "提示：第一个会话的头像中心大约在y=97，每个会话间隔约35。"
        "直接输出JSON格式结果。"
        'JSON格式：{"threads": [{"name": "会话名称", "y": 97, "is_group": true/false, "unread": true/false}, ...]}'
        "只输出JSON，不要输出其他文字。"
    )


def parse_classification(
    text_output: str, image_height: int = 1440
) -> List[GroupThread]:
    """Parse classification output and convert normalized y to pixels.

    Args:
        text_output: JSON string from AI with y in 0-1000 normalized space
        image_height: Height of the cropped image in pixels (default 1440)
    """
    text = text_output.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json or ```) and last line (```)
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    payload = json.loads(text)
    # Handle both formats: {"threads": [...]} or direct array [...]
    if isinstance(payload, list):
        raw_threads = payload
    else:
        raw_threads = payload.get("threads", [])

    threads = []
    for item in raw_threads:
        # Convert from 0-1000 normalized space to pixel space
        normalized_y = item.get("y", 0)
        pixel_y = int((normalized_y / 1000.0) * image_height)

        threads.append(
            GroupThread(
                name=str(item.get("name", "")),
                thread_id=str(item.get("thread_id", item.get("name", ""))),
                unread=bool(item.get("unread", False)),
                is_group=bool(item.get("is_group", False)),
                y=pixel_y,
            )
        )
    return threads
