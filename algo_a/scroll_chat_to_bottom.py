"""Scroll the chat message panel to the very bottom to load all messages.

Usage:
    from algo_a.scroll_chat_to_bottom import scroll_chat_to_bottom
    scroll_chat_to_bottom(window)

Input spec:
    - window: WechatWindow reference from platform_mac.

Output spec:
    - None. Side effect: the message scroll area is at the bottom.

Notes:
    - WeChat lazy-loads messages as you scroll. This function must scroll
      incrementally upward first (to load history), then back to bottom,
      or scroll down until no new content appears.
"""

from platform_mac.find_wechat_window import WechatWindow


def scroll_chat_to_bottom(window: WechatWindow) -> None:
    """Scroll the right-side message area to the very bottom."""
    assert window is not None
    raise NotImplementedError(
        "find the message AXScrollArea, repeatedly perform AXScrollDown "
        "until scroll position stops changing"
    )
