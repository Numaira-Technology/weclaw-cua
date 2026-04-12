"""Deduplicate ChatMessage lists after vision extraction.

Usage:
    from shared.message_dedup import dedupe_chat_messages
    dedupe_chat_messages(messages)
"""

from shared.datatypes import ChatMessage


def dedupe_chat_messages(messages: list[ChatMessage]) -> list[ChatMessage]:
    seen: set[tuple] = set()
    out: list[ChatMessage] = []
    for m in messages:
        k = (m.sender, m.time, m.content, m.type)
        if k in seen:
            continue
        seen.add(k)
        out.append(m)
    return out
