"""
Windows-specific implementation of the PlatformDriver protocol.
"""
from typing import Any

from shared.platform_api import PlatformDriver


class WinDriver(PlatformDriver):

    def ensure_permissions(self) -> None:
        raise NotImplementedError

    def find_wechat_window(self, app_name: str) -> Any:
        raise NotImplementedError

    def get_sidebar_rows(self, window: Any) -> list[Any]:
        raise NotImplementedError

    def scroll_sidebar(self, window: Any, direction: str) -> None:
        raise NotImplementedError

    def get_row_name(self, row: Any) -> str:
        raise NotImplementedError

    def get_row_badge_text(self, row: Any) -> str | None:
        raise NotImplementedError

    def click_row(self, row: Any) -> None:
        raise NotImplementedError

    def get_message_elements(self, window: Any) -> list[Any]:
        raise NotImplementedError

    def scroll_messages(self, window: Any, direction: str) -> None:
        raise NotImplementedError

    def get_message_scroll_position(self, window: Any) -> float:
        raise NotImplementedError

    def get_element_role(self, element: Any) -> str:
        raise NotImplementedError

    def get_element_text(self, element: Any) -> str | None:
        raise NotImplementedError

    def get_element_children(self, element: Any) -> list[Any]:
        raise NotImplementedError

    def wait_for_message_panel_ready(self, window: Any) -> None:
        raise NotImplementedError
