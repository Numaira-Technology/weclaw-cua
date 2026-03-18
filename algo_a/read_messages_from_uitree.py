"""Walk the message list AXUIElements and extract structured message data.

Usage:
    from algo_a.read_messages_from_uitree import read_messages_from_uitree
    messages = read_messages_from_uitree(window, "Group A")

Input spec:
    - window: WechatWindow reference from platform_mac.
    - chat_name: name of the currently active chat (used to tag messages).

Output spec:
    - Returns list[dict] where each dict has keys:
      chat_name, sender, time, content, type.
    - type is one of: "text", "system", "link_card", "image", "unsupported".
    - Messages are in chronological order (top to bottom in the UI).

Notes:
    - Each message bubble is typically an AXGroup containing AXStaticText children.
    - System messages (date separators, join notices) have a different AX structure.
    - Link cards and images should be identified by their AXRole subtree shape.
"""

from platform_mac.find_wechat_window import WechatWindow


def read_messages_from_uitree(window: WechatWindow, chat_name: str) -> list[dict]:
    """Extract all visible messages from the active chat's UI tree."""
    assert window is not None
    assert chat_name
    raise NotImplementedError(
        "find message AXScrollArea > AXList, iterate children, "
        "classify each as text/system/link_card/image/unsupported, "
        "extract sender + time + content from AX attributes"
    )
