"""Click a chat row in the WeChat sidebar to open it in the message panel.

Usage:
    from algo_a.click_into_chat import click_into_chat
    click_into_chat(driver, window, chat)

Input spec:
    - driver: PlatformDriver instance.
    - window: platform-specific window handle.
    - chat: ChatInfo with a valid ui_element reference to the sidebar row.

Output spec:
    - None. Side effect: the chat is now the active conversation in the right panel.
    - Blocks until the message panel is ready for reading.
"""

from shared.platform_api import PlatformDriver
from algo_a.list_unread_chats import ChatInfo
from typing import Any


def click_into_chat(driver: PlatformDriver, window: Any, chat: ChatInfo) -> None:
    """Click a sidebar row and wait for the message panel to load."""
    assert chat is not None
    assert chat.ui_element is not None

    driver.click_row(chat.ui_element)
    driver.wait_for_message_panel_ready(window)
