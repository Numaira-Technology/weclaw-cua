from dataclasses import dataclass


@dataclass
class SidebarRow:
    """Represents a single chat row in the sidebar, identified by the Vision AI."""
    name: str
    last_message: str | None
    badge_text: str | None
    bbox: tuple[int, int, int, int]  # Absolute screen coordinates


@dataclass
class Chat:
    """Represents a chat to be monitored."""
    name: str
    strategy: str
    config: dict
