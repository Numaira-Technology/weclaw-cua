"""Platform-agnostic interface that platform_mac/ and platform_win/ must implement.

Usage:
    from shared.platform_api import PlatformDriver

    class MacDriver(PlatformDriver):
        ...

Each platform package must provide a top-level `create_driver() -> PlatformDriver`
function in its __init__.py.

The PlatformDriver protocol defines the minimal surface algo_a needs:
    - ensure_permissions()
    - find_wechat_window(app_name) -> window handle
    - get_sidebar_rows(window) -> list of UI element handles
    - scroll_sidebar(window, direction) -> None
    - get_row_name(row) -> str
    - get_row_badge_text(row) -> str | None
    - click_row(row) -> None
    - get_message_elements(window) -> list of UI element handles
    - scroll_messages(window, direction) -> None
    - get_message_scroll_position(window) -> float
    - get_element_role(element) -> str
    - get_element_text(element) -> str | None
    - get_element_children(element) -> list
    - wait_for_message_panel_ready(window) -> None
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class PlatformDriver(Protocol):

    def ensure_permissions(self) -> None:
        """Assert platform prerequisites (Accessibility on mac, admin on win)."""
        ...

    def find_wechat_window(self, app_name: str) -> Any:
        """Locate the WeChat window. Returns a platform-specific window handle."""
        ...

    def get_sidebar_rows(self, window: Any) -> list[Any]:
        """Return currently visible chat rows in the sidebar list."""
        ...

    def scroll_sidebar(self, window: Any, direction: str) -> None:
        """Scroll the sidebar. direction is 'up' or 'down'."""
        ...

    def get_row_name(self, row: Any) -> str:
        """Extract the chat name from a sidebar row element."""
        ...

    def get_row_badge_text(self, row: Any) -> str | None:
        """Return the badge text ('3', '99+', etc.) or None if no badge.

        For muted chats with a dot but no number, return empty string ''.
        For chats with no unread indicator at all, return None.
        """
        ...

    def click_row(self, row: Any) -> None:
        """Click/activate a sidebar row to open that chat."""
        ...

    def get_message_elements(self, window: Any) -> list[Any]:
        """Return the ordered list of message bubble elements in the active chat."""
        ...

    def scroll_messages(self, window: Any, direction: str) -> None:
        """Scroll the message panel. direction is 'up' or 'down'."""
        ...


