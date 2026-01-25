"""
Read unread messages inside a specific group thread and surface suspects.

Usage:
  prompt = message_reader_prompt(thread)

Input:
  - thread: GroupThread representing an unread group chat.

Output:
  - Prompt string instructing the agent to open the thread, scroll through unread messages, and return JSON with suspects: [{sender_id, sender_name, evidence_text}].
"""

from __future__ import annotations

from modules.task_types import GroupThread


def message_reader_prompt(thread: GroupThread) -> str:
    return (
        f"任务：检查群聊 {thread.name} 中的未读消息。\n\n"
        "步骤：\n"
        "1. 点击进入该群聊\n"
        "2. 查看当前屏幕上的消息内容\n"
        "3. 如果发现包含「代写」的信息，记录发送者信息\n\n"
        "重要：只执行1-2次点击操作，然后立即返回结果。不要反复点击同一个位置。\n\n"
        "完成后，直接输出JSON结果（不要再执行任何点击）：\n"
        f'{{"thread_id": "{thread.thread_id}", "suspects": [{{"sender_id": "xxx", "sender_name": "xxx", "evidence_text": "xxx"}}]}}\n\n'
        "如果没有发现可疑消息，返回空数组：\n"
        f'{{"thread_id": "{thread.thread_id}", "suspects": []}}'
    )
