"""Capture sequential screenshots while scrolling through unread messages.

Usage:
    Call this after locating the unread start marker.

Input spec:
    - `group_name`: target WeChat group name.
    - `unread_marker`: marker returned by `locate_unread_position()`.

Output spec:
    - Returns screenshot file paths in capture order.
"""


def capture_scroll_screenshots(group_name: str, unread_marker: str) -> list[str]:
    assert group_name
    assert unread_marker
    raise NotImplementedError("Implement scrolling screenshot capture.")
