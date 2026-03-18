"""Message dataclass and JSON serialization helpers.

Usage:
    from shared.message_schema import Message, messages_to_json, messages_from_json

Input spec:
    - Message fields: chat_name, sender, time (nullable), content, type.
    - type is one of: "text", "system", "link_card", "image", "unsupported".

Output spec:
    - messages_to_json: list[Message] -> JSON string.
    - messages_from_json: JSON string -> list[Message].
"""

import json
from dataclasses import asdict, dataclass


VALID_MESSAGE_TYPES = {"text", "system", "link_card", "image", "unsupported"}


@dataclass
class Message:
    chat_name: str
    sender: str
    time: str | None
    content: str
    type: str

    def __post_init__(self) -> None:
        assert self.type in VALID_MESSAGE_TYPES, f"invalid type: {self.type}"


def messages_to_json(messages: list[Message]) -> str:
    assert isinstance(messages, list)
    return json.dumps([asdict(m) for m in messages], ensure_ascii=False, indent=2)


def messages_from_json(json_str: str) -> list[Message]:
    assert json_str
    raw = json.loads(json_str)
    assert isinstance(raw, list)
    return [Message(**entry) for entry in raw]
