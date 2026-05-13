import json

from shared.chat_chunk_extraction import extract_messages_from_captured_chat
from shared.datatypes import CapturedChatImages, ChatImageChunk


class FakeVisionBackend:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def query(self, prompt: str, image: object, max_tokens: int = 2048) -> str:
        assert prompt
        assert image is not None
        assert max_tokens == 16384
        return json.dumps(self.payload, ensure_ascii=False)


def test_extract_messages_skips_cutoff_normal_message_without_sender() -> None:
    captured = CapturedChatImages(
        chat_name="SDG",
        chunks=[ChatImageChunk(chunk_index=0, chunk_total=1, image=object())],
    )
    backend = FakeVisionBackend({
        "messages": [
            {"sender": None, "content": "聊两句呗哥", "time": None, "type": "text"},
            {"sender": None, "content": "16:15", "time": "16:15", "type": "system"},
            {"sender": "AARON", "content": "@Pauline 待会儿电话拨入@Frank", "time": None, "type": "text"},
            {"sender": "You", "content": "收到", "time": None, "type": "text"},
        ],
    })

    messages = extract_messages_from_captured_chat(captured, backend)

    assert [(m.sender, m.content, m.time, m.type) for m in messages] == [
        ("AARON", "@Pauline 待会儿电话拨入@Frank", "16:15", "text"),
        ("You", "收到", "16:15", "text"),
    ]


def test_extract_messages_keeps_centered_system_notice_without_sender() -> None:
    captured = CapturedChatImages(
        chat_name="SDG",
        chunks=[ChatImageChunk(chunk_index=0, chunk_total=1, image=object())],
    )
    backend = FakeVisionBackend({
        "messages": [
            {"sender": None, "content": "Yesterday 22:08", "time": "Yesterday 22:08", "type": "system"},
            {"sender": None, "content": "语音通话已经结束", "time": None, "type": "system"},
            {"sender": "Pauline", "content": "@AARON", "time": None, "type": "text"},
        ],
    })

    messages = extract_messages_from_captured_chat(captured, backend)

    assert [(m.sender, m.content, m.time, m.type) for m in messages] == [
        (None, "语音通话已经结束", "Yesterday 22:08", "system"),
        ("Pauline", "@AARON", "Yesterday 22:08", "text"),
    ]


def test_extract_messages_keeps_centered_recalled_notice_without_sender() -> None:
    captured = CapturedChatImages(
        chat_name="SDG",
        chunks=[ChatImageChunk(chunk_index=0, chunk_total=1, image=object())],
    )
    backend = FakeVisionBackend({
        "messages": [
            {"sender": None, "content": "Yesterday 22:08", "time": "Yesterday 22:08", "type": "system"},
            {"sender": None, "content": "You recalled a message", "time": None, "type": "recalled"},
            {"sender": "Pauline", "content": "@AARON", "time": None, "type": "text"},
        ],
    })

    messages = extract_messages_from_captured_chat(captured, backend)

    assert [(m.sender, m.content, m.time, m.type) for m in messages] == [
        (None, "You recalled a message", "Yesterday 22:08", "recalled"),
        ("Pauline", "@AARON", "Yesterday 22:08", "text"),
    ]
