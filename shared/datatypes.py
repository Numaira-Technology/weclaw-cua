from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class SidebarRow:
    """Represents a single chat row in the sidebar, identified by the Vision AI."""

    name: str
    last_message: str | None
    badge_text: str | None
    bbox: tuple[int, int, int, int]
    # None = unknown (e.g. macOS Vision OCR fast path); filtering should not drop the row.
    is_group: Optional[bool] = None
    selected: bool = False


@dataclass
class ChatMessage:
    """Represents a single message in the chat panel."""
    sender: str | None  # None for system messages (e.g., timestamps)
    content: str
    time: str | None
    type: str  # e.g., 'text', 'image', 'file', 'system'


@dataclass
class ChatImageChunk:
    """A stitched chat-image chunk ready for message extraction."""

    chunk_index: int
    chunk_total: int
    image: Any


@dataclass
class CapturedChatImages:
    """Captured/stitched images for one chat, before VLM message extraction."""

    chat_name: str
    chunks: list[ChatImageChunk]
    max_messages: int | None = None


@dataclass
class Chat:
    """Represents a chat to be monitored."""
    name: str
    strategy: str
    config: dict
