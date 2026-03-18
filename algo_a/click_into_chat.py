"""Click a chat row in the WeChat sidebar to open it in the message panel.

Usage:
    from algo_a.click_into_chat import click_into_chat
    click_into_chat(chat)

Input spec:
    - chat: ChatInfo with a valid ui_element reference to the sidebar row.

Output spec:
    - None. Side effect: the chat is now the active conversation in the right panel.
"""

from algo_a.list_unread_chats import ChatInfo


def click_into_chat(chat: ChatInfo) -> None:
    """Perform AXPress on the chat sidebar row to open the conversation."""
    assert chat is not None
    assert chat.ui_element is not None
    raise NotImplementedError("perform_action(chat.ui_element, 'AXPress')")
