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
        "请仔细观察当前屏幕上的微信会话列表截图。"
        "不要点击任何东西，只需要分析截图中可见的会话。"
        "使用头像图标区分群聊（多人头像）与单聊（单人头像）。"
        "记录每个会话的未读状态（是否有未读消息标记）。"
        "直接输出JSON格式结果，不要执行任何点击操作。"
        "JSON格式：{\"threads\": [{\"thread_id\": \"会话名称\", \"name\": \"会话名称\", \"is_group\": true/false, \"unread\": true/false}, ...]}"
        "只输出JSON，不要输出其他文字。"
    )


def parse_classification(text_output: str) -> List[GroupThread]:
    payload = json.loads(text_output)
    raw_threads = payload.get("threads", [])
    return [
        GroupThread(
            name=str(item.get("name", "")),
            thread_id=str(item.get("thread_id", "")),
            unread=bool(item.get("unread", False)),
            is_group=bool(item.get("is_group", False)),
        )
        for item in raw_threads
    ]
