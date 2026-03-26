from dataclasses import dataclass


@dataclass
class SidebarRow:
    """Represents a single chat row in the sidebar, identified by the Vision AI."""
    name: str
    last_message: str | None
    badge_text: str | None
    bbox: tuple[int, int, int, int]  # Bounding box relative to the sidebar image crop


@dataclass
class ChatMessage:
    """Represents a single message in the chat panel."""
    sender: str | None  # None for system messages (e.g., timestamps)
    content: str
    time: str | None
    type: str  # e.g., 'text', 'image', 'file', 'system'


@dataclass
class Chat:
    """Represents a chat to be monitored."""
    name: str
    strategy: str
    config: dict
