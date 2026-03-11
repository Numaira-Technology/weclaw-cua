"""Check whether a target group has unread messages.

Usage:
    Call this before running the screenshot and extraction steps.

Input spec:
    - `group_name`: target WeChat group name.

Output spec:
    - Returns `True` when the group has new messages, else `False`.
"""


def detect_new_messages(group_name: str) -> bool:
    assert group_name
    raise NotImplementedError("Implement unread-message detection.")
