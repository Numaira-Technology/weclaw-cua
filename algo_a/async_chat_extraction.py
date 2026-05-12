"""Async message extraction queue for direct capture pipelines."""

from __future__ import annotations

import json
import os
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass
from typing import Any

from shared.datatypes import ChatMessage


@dataclass
class PendingChatWrite:
    output_index: int
    chat_name: str
    captured: Any
    recent_window_hours: int = 0


@dataclass
class ChatWriteResult:
    output_index: int
    chat_name: str
    success: bool
    json_path: str = ""
    message_count: int = 0
    error: str = ""


def async_vlm_worker_count() -> int:
    raw = os.environ.get("WECLAW_ASYNC_VLM_WORKERS", "").strip()
    if not raw:
        return 2 # default number of workers
    value = int(raw)
    assert value >= 0, "WECLAW_ASYNC_VLM_WORKERS must be >= 0"
    return value


def async_vlm_max_pending(worker_count: int) -> int:
    raw = os.environ.get("WECLAW_ASYNC_VLM_MAX_PENDING", "").strip()
    if raw:
        value = int(raw)
        assert value >= 1, "WECLAW_ASYNC_VLM_MAX_PENDING must be >= 1"
        return value
    return max(30, worker_count + 1) # default queue length


def sanitize_chat_json_filename(name: str, fallback: str) -> str:
    """Stable JSON basename: keeps Unicode including emoji/CJK; only strips illegal path chars."""
    s = str(name or "").strip()
    if not s:
        return fallback
    forbidden = '\\/:*?"<>|'
    parts: list[str] = []
    for ch in s:
        if ch in forbidden or ord(ch) < 32:
            parts.append("_")
        else:
            parts.append(ch)
    s = "".join(parts).rstrip(". ").strip()
    return s if s else fallback


def write_chat_messages_json(
    *,
    output_dir: str,
    chat_name: str,
    messages: list[ChatMessage],
    output_index: int,
    persist_chat_name: str | None = None,
) -> str:
    """persist_chat_name, when set, is used for the filename and message chat_name fields (config label)."""
    display_name = (
        str(persist_chat_name).strip()
        if (persist_chat_name is not None and str(persist_chat_name).strip())
        else chat_name
    )
    fallback = f"chat_{output_index}"
    safe_filename = sanitize_chat_json_filename(display_name, fallback)
    output_path = os.path.join(output_dir, f"{safe_filename}.json")
    os.makedirs(output_dir, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        rows_out = []
        for msg in messages:
            d = asdict(msg)
            d["chat_name"] = display_name
            d["sender"] = d["sender"] or ""
            rows_out.append(d)
        json.dump(rows_out, f, ensure_ascii=False, indent=2)
    return output_path


class AsyncChatExtractionQueue:
    def __init__(
        self,
        *,
        driver: Any,
        output_dir: str,
        max_workers: int,
        max_pending: int,
    ) -> None:
        assert max_workers > 0
        assert max_pending >= 1
        self.driver = driver
        self.output_dir = output_dir
        self.max_pending = max_pending
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="weclaw-vlm",
        )
        self._pending: list[Future[ChatWriteResult]] = []
        print(
            f"[*] Async VLM extraction enabled: workers={max_workers}, "
            f"max_pending={max_pending}."
        )

    def submit(self, job: PendingChatWrite) -> list[ChatWriteResult]:
        completed: list[ChatWriteResult] = []
        while len(self._pending) >= self.max_pending:
            completed.append(self._wait_oldest())
        self._pending.append(self._pool.submit(self._run_job, job))
        print(f"[*] Queued VLM extraction for {job.chat_name!r}.")
        return completed

    def drain(self) -> list[ChatWriteResult]:
        completed: list[ChatWriteResult] = []
        while self._pending:
            completed.append(self._wait_oldest())
        self._pool.shutdown(wait=True)
        return completed

    def _wait_oldest(self) -> ChatWriteResult:
        future = self._pending.pop(0)
        return future.result()

    def _run_job(self, job: PendingChatWrite) -> ChatWriteResult:
        try:
            messages = self.driver.extract_chat_messages_from_capture(
                job.captured,
                recent_window_hours=job.recent_window_hours,
            )
            if not messages:
                return ChatWriteResult(
                    output_index=job.output_index,
                    chat_name=job.chat_name,
                    success=False,
                    error="no_messages_extracted",
                )
            output_path = write_chat_messages_json(
                output_dir=self.output_dir,
                chat_name=job.chat_name,
                messages=messages,
                output_index=job.output_index,
            )
            print(
                f"[SUCCESS] Successfully saved {len(messages)} messages to {output_path}"
            )
            return ChatWriteResult(
                output_index=job.output_index,
                chat_name=job.chat_name,
                success=True,
                json_path=output_path,
                message_count=len(messages),
            )
        except Exception as e:
            return ChatWriteResult(
                output_index=job.output_index,
                chat_name=job.chat_name,
                success=False,
                error=f"{type(e).__name__}: {e}",
            )


def can_capture_async(driver: Any) -> bool:
    return callable(getattr(driver, "capture_chat_messages", None)) and callable(
        getattr(driver, "extract_chat_messages_from_capture", None)
    )


def make_async_queue(driver: Any, output_dir: str) -> AsyncChatExtractionQueue | None:
    worker_count = async_vlm_worker_count()
    if worker_count <= 0:
        print("[*] Async VLM extraction disabled by WECLAW_ASYNC_VLM_WORKERS=0.")
        return None
    if not can_capture_async(driver):
        print("[WARN] Driver does not expose async capture/extract hooks; using synchronous extraction.")
        return None
    return AsyncChatExtractionQueue(
        driver=driver,
        output_dir=output_dir,
        max_workers=worker_count,
        max_pending=async_vlm_max_pending(worker_count),
    )


def record_chat_write_results(
    results: list[ChatWriteResult],
    written_paths: list[str],
) -> None:
    for result in sorted(results, key=lambda item: item.output_index):
        if result.success:
            written_paths.append(result.json_path)
        else:
            print(
                f"[WARN] Async extraction failed for {result.chat_name!r}: "
                f"{result.error or 'unknown error'}"
            )
