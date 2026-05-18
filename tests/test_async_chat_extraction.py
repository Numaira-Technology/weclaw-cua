import time
from threading import Event
from types import SimpleNamespace

import algo_a.async_chat_extraction as async_chat_extraction
from algo_a.async_chat_extraction import (
    AsyncChatExtractionQueue,
    PendingChatWrite,
    async_vlm_worker_count,
    sanitize_chat_json_filename,
)
from PIL import Image

from shared.chat_chunk_extraction import extract_messages_from_captured_chat
from shared.datatypes import CapturedChatImages, ChatImageChunk, ChatMessage


def test_sanitize_chat_json_filename_keeps_cjk_and_emoji() -> None:
    name = "\U0001f5fd纽约2025艺术新生交流群"
    assert sanitize_chat_json_filename(name, "fb") == name


def test_sanitize_chat_json_filename_strips_illegal_chars() -> None:
    assert sanitize_chat_json_filename('a:b/c', "fb") == "a_b_c"


def test_async_vlm_worker_count_rejects_zero(monkeypatch) -> None:
    monkeypatch.setenv("WECLAW_ASYNC_VLM_WORKERS", "0")

    try:
        async_vlm_worker_count()
    except AssertionError as e:
        assert "WECLAW_ASYNC_VLM_WORKERS must be >= 1" in str(e)
    else:
        raise AssertionError("expected WECLAW_ASYNC_VLM_WORKERS=0 to fail")


class SlowFakeDriver:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def extract_chat_messages_from_capture(
        self,
        captured: object,
        *,
        recent_window_hours: int = 0,
    ) -> list[ChatMessage]:
        chat_name = str(getattr(captured, "chat_name"))
        self.calls.append(chat_name)
        time.sleep(0.2)
        return [ChatMessage(sender="Alice", content=chat_name, time=None, type="text")]


class FastFakeDriver:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def extract_chat_messages_from_capture(
        self,
        captured: object,
        *,
        recent_window_hours: int = 0,
    ) -> list[ChatMessage]:
        chat_name = str(getattr(captured, "chat_name"))
        self.calls.append(chat_name)
        return [ChatMessage(sender="Alice", content=chat_name, time=None, type="text")]


class MixedFakeDriver:
    def extract_chat_messages_from_capture(
        self,
        captured: object,
        *,
        recent_window_hours: int = 0,
    ) -> list[ChatMessage]:
        chat_name = str(getattr(captured, "chat_name"))
        if chat_name == "bad":
            raise RuntimeError("boom")
        return [ChatMessage(sender="Alice", content=chat_name, time=None, type="text")]


class RecordingRecentWindowDriver:
    def __init__(self) -> None:
        self.recent_windows: list[int] = []

    def extract_chat_messages_from_capture(
        self,
        captured: object,
        *,
        recent_window_hours: int = 0,
    ) -> list[ChatMessage]:
        self.recent_windows.append(recent_window_hours)
        return [ChatMessage(sender="Alice", content="ok", time=None, type="text")]


class CountingVision:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def query(self, prompt: str, image: Image.Image, max_tokens: int = 2048) -> str:
        assert prompt
        assert image
        assert max_tokens == 16384
        self.calls.append(len(self.calls))
        return '{"messages":[{"sender":"Alice","content":"hello","type":"text"}]}'


def test_queue_submit_does_not_wait_for_slow_vlm(tmp_path) -> None:
    driver = SlowFakeDriver()
    queue = AsyncChatExtractionQueue(
        driver=driver,
        output_dir=str(tmp_path),
        max_workers=1,
        max_pending=2,
    )

    started = time.perf_counter()
    queue.submit(PendingChatWrite(1, "one", SimpleNamespace(chat_name="one")))
    queue.submit(PendingChatWrite(2, "two", SimpleNamespace(chat_name="two")))
    elapsed = time.perf_counter() - started

    results = queue.drain()

    assert elapsed < 0.15
    assert [r.chat_name for r in results] == ["one", "two"]
    assert all(r.success for r in results)
    assert driver.calls == ["one", "two"]


def test_vlm_worker_does_not_wait_for_json_write(tmp_path, monkeypatch) -> None:
    driver = FastFakeDriver()
    write_started = Event()
    release_write = Event()
    original_write = async_chat_extraction.write_chat_messages_json

    def blocking_write(**kwargs):
        if kwargs["chat_name"] == "one":
            write_started.set()
            assert release_write.wait(2)
        return original_write(**kwargs)

    monkeypatch.setattr(async_chat_extraction, "write_chat_messages_json", blocking_write)
    queue = AsyncChatExtractionQueue(
        driver=driver,
        output_dir=str(tmp_path),
        max_workers=1,
        max_pending=2,
        write_workers=1,
    )

    queue.submit(PendingChatWrite(1, "one", SimpleNamespace(chat_name="one")))
    assert write_started.wait(1)
    queue.submit(PendingChatWrite(2, "two", SimpleNamespace(chat_name="two")))

    deadline = time.perf_counter() + 1
    while len(driver.calls) < 2 and time.perf_counter() < deadline:
        time.sleep(0.01)

    release_write.set()
    results = queue.drain()

    assert driver.calls == ["one", "two"]
    assert [(r.chat_name, r.success) for r in results] == [("one", True), ("two", True)]


def test_queue_failure_does_not_stop_other_jobs(tmp_path) -> None:
    queue = AsyncChatExtractionQueue(
        driver=MixedFakeDriver(),
        output_dir=str(tmp_path),
        max_workers=1,
        max_pending=3,
    )

    queue.submit(PendingChatWrite(1, "ok", SimpleNamespace(chat_name="ok")))
    queue.submit(PendingChatWrite(2, "bad", SimpleNamespace(chat_name="bad")))
    queue.submit(PendingChatWrite(3, "later", SimpleNamespace(chat_name="later")))
    results = queue.drain()

    assert [(r.chat_name, r.success) for r in results] == [
        ("ok", True),
        ("bad", False),
        ("later", True),
    ]


def test_queue_passes_recent_window_to_extractor(tmp_path) -> None:
    driver = RecordingRecentWindowDriver()
    queue = AsyncChatExtractionQueue(
        driver=driver,
        output_dir=str(tmp_path),
        max_workers=1,
        max_pending=1,
    )

    queue.submit(
        PendingChatWrite(
            output_index=1,
            chat_name="recent",
            captured=SimpleNamespace(chat_name="recent"),
            recent_window_hours=24,
        )
    )
    result = queue.drain()[0]

    assert result.success
    assert driver.recent_windows == [24]


def test_message_extraction_calls_vlm_once_per_chunk() -> None:
    vision = CountingVision()
    image = Image.new("RGB", (10, 10), "white")
    captured = CapturedChatImages(
        chat_name="chunked",
        chunks=[
            ChatImageChunk(chunk_index=0, chunk_total=3, image=image),
            ChatImageChunk(chunk_index=1, chunk_total=3, image=image),
            ChatImageChunk(chunk_index=2, chunk_total=3, image=image),
        ],
    )

    messages = extract_messages_from_captured_chat(captured, vision)

    assert len(messages) == 1
    assert len(vision.calls) == 3
