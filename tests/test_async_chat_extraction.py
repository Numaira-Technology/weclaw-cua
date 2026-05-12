import time
from types import SimpleNamespace

from algo_a.async_chat_extraction import (
    AsyncChatExtractionQueue,
    PendingChatWrite,
    sanitize_chat_json_filename,
)
from shared.datatypes import ChatMessage


def test_sanitize_chat_json_filename_keeps_cjk_and_emoji() -> None:
    name = "\U0001f5fd纽约2025艺术新生交流群"
    assert sanitize_chat_json_filename(name, "fb") == name


def test_sanitize_chat_json_filename_strips_illegal_chars() -> None:
    assert sanitize_chat_json_filename('a:b/c', "fb") == "a_b_c"


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
