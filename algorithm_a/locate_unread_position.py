"""Locate the UI position where unread messages begin.

Usage:
    Call this after new-message detection and before scrolling screenshots.

Input spec:
    - `group_name`: target WeChat group name.

Output spec:
    - Returns a string marker that identifies the unread start position.
"""


def locate_unread_position(group_name: str) -> str:
    assert group_name
    raise NotImplementedError("Implement unread-position discovery.")
