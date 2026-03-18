"""macOS PlatformDriver implementation using Accessibility API (pyobjc).

Usage:
    from platform_mac.driver import MacDriver
    driver = MacDriver()

Implements shared.platform_api.PlatformDriver.
All methods raise NotImplementedError — this is the file you need to implement.
See algo_a/DEVGUIDE.md for detailed instructions.
"""

from typing import Any

from platform_mac.grant_permissions import ensure_permissions as _ensure_permissions
from platform_mac.find_wechat_window import find_wechat_window as _find_wechat_window


class MacDriver:

    def ensure_permissions(self) -> None:
        _ensure_permissions()

    def find_wechat_window(self, app_name: str) -> Any:
        return _find_wechat_window(app_name)

    def get_sidebar_rows(self, window: Any) -> list[Any]:
        """Navigate to the sidebar AXList inside the window and return its AXRow children.

        Typical AX path: window_ref -> AXSplitGroup -> first AXScrollArea -> AXList -> AXRow[]
        """
        raise NotImplementedError

    def scroll_sidebar(self, window: Any, direction: str) -> None:
        """Scroll the sidebar AXScrollArea. Use perform_action(scroll_area, 'AXScrollDown')
        or CGEvent scroll wheel events targeting the sidebar region."""
        assert direction in ("up", "down")
        raise NotImplementedError

    def get_row_name(self, row: Any) -> str:
        """Read AXTitle or AXValue from the row, or find the AXStaticText child
        that contains the chat name."""
        raise NotImplementedError

    def get_row_badge_text(self, row: Any) -> str | None:
        """Look for a badge child element in the row.

        No badge element at all -> return None.
        Badge element exists but has no AXValue/AXTitle text -> return '' (muted dot).
        Badge element has text like '3' or '99+' -> return that text.
        """
        raise NotImplementedError

    def click_row(self, row: Any) -> None:
        """Perform AXPress action on the row element."""
        raise NotImplementedError

    def get_message_elements(self, window: Any) -> list[Any]:
        """Navigate to the message panel's AXScrollArea -> AXList and return children.

        Typical AX path: window_ref -> AXSplitGroup -> second AXScrollArea -> AXList -> children
        """
        raise NotImplementedError

    def scroll_messages(self, window: Any, direction: str) -> None:
        """Scroll the message panel AXScrollArea."""
        assert direction in ("up", "down")
        raise NotImplementedError

    def get_message_scroll_position(self, window: Any) -> float:
        """Read AXValue from the message AXScrollArea's vertical AXScrollBar.

        AXValue is a float from 0.0 (top) to 1.0 (bottom).
        """
        raise NotImplementedError

    def get_element_role(self, element: Any) -> str:
        """Return AXRole attribute of the element."""
        raise NotImplementedError

    def get_element_text(self, element: Any) -> str | None:
        """Return AXValue or AXTitle of the element, whichever is non-empty."""
        raise NotImplementedError

    def get_element_children(self, element: Any) -> list[Any]:
        """Return AXChildren attribute of the element."""
        raise NotImplementedError

    def wait_for_message_panel_ready(self, window: Any) -> None:
        """Poll until the message panel's content stabilizes after a chat switch.

        Strategy: read message element count, sleep 200ms, re-read, repeat
        until count is stable for 2 consecutive reads.
        """
        raise NotImplementedError
