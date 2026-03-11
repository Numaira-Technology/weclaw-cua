"""Write extracted messages into the group JSON store.

Usage:
    Call this after message extraction finishes for one group.

Input spec:
    - `group_name`: target WeChat group name.
    - `messages`: extracted message dictionaries.

Output spec:
    - Returns the JSON file path that was written or updated.
"""


def write_group_json(group_name: str, messages: list[dict[str, str]]) -> str:
    assert group_name
    assert messages
    raise NotImplementedError("Implement group JSON persistence.")
