"""Data model for ranked chat-message context chunks.

Usage:
    from shared.message_context_chunk import MessageContextChunk

Input spec:
    - chat/source_path identify the captured message file.
    - center_index points to the best-matching message in that file.
    - messages contains the cited message window.

Output spec:
    - MessageContextChunk is serializable with dataclasses.asdict.
"""

from dataclasses import dataclass


@dataclass
class MessageContextChunk:
    chat: str
    source_path: str
    center_index: int
    score: float
    matched_terms: list[str]
    messages: list[dict]
