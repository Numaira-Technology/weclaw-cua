"""Async capture, VLM extraction, and JSON write pipeline for direct capture."""

from __future__ import annotations

import json
import os
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass
from threading import Lock
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


@dataclass
class PendingChatMessages:
    output_index: int
    chat_name: str
    messages: list[ChatMessage]


def async_vlm_worker_count() -> int:
    raw = os.environ.get("WECLAW_ASYNC_VLM_WORKERS", "").strip()
    if not raw:
        return 2 # default number of workers
    value = int(raw)
    assert value >= 1, "WECLAW_ASYNC_VLM_WORKERS must be >= 1"
    return value


def async_json_worker_count() -> int:
    raw = os.environ.get("WECLAW_ASYNC_JSON_WORKERS", "").strip()
    if not raw:
        return 1
    value = int(raw)
    assert value >= 1, "WECLAW_ASYNC_JSON_WORKERS must be >= 1"
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
        write_workers: int = 1,
    ) -> None:
        assert max_workers > 0
        assert max_pending >= 1
        assert write_workers > 0
        self.driver = driver
        self.output_dir = output_dir
        self.max_pending = max_pending
        self._vlm_pool = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="weclaw-vlm",
        )
        self._write_pool = ThreadPoolExecutor(
            max_workers=write_workers,
            thread_name_prefix="weclaw-json",
        )
        self._pending_vlm: list[Future[None]] = []
        self._pending_write: list[Future[ChatWriteResult]] = []
        self._completed: list[ChatWriteResult] = []
        self._lock = Lock()
        print(
            f"[*] Async capture pipeline enabled: vlm_workers={max_workers}, "
            f"json_workers={write_workers}, max_pending={max_pending}."
        )

    def submit(self, job: PendingChatWrite) -> list[ChatWriteResult]:
        while self._vlm_backlog_count() >= self.max_pending:
            self._wait_oldest_vlm()
        future = self._vlm_pool.submit(self._run_vlm_job, job)
        with self._lock:
            self._pending_vlm.append(future)
        print(f"[*] Queued VLM extraction for {job.chat_name!r}.")
        return []

    def capture_and_submit(
        self,
        chat_name: str,
        *,
        output_index: int,
        max_messages: int | None = None,
        max_scrolls: int | None = None,
        recent_window_hours: int = 0,
        skip_navigation_vlm: bool = False,
        persist_chat_name: str | None = None,
    ) -> bool:
        captured = self.driver.capture_chat_messages(
            chat_name,
            max_messages=max_messages,
            max_scrolls=max_scrolls,
            skip_navigation_vlm=skip_navigation_vlm,
        )
        if getattr(captured, "chunks", None) == []:
            print(f"[WARN] No screenshots were captured for {chat_name!r}.")
            return False
        persist = (
            str(persist_chat_name).strip()
            if persist_chat_name is not None and str(persist_chat_name).strip()
            else chat_name
        )
        self.submit(
            PendingChatWrite(
                output_index=output_index,
                chat_name=persist,
                captured=captured,
                recent_window_hours=recent_window_hours,
            )
        )
        return True

    def drain(self) -> list[ChatWriteResult]:
        for vlm_future in self._vlm_futures():
            vlm_future.result()
        for write_future in self._write_futures():
            self._completed.append(write_future.result())
        self._vlm_pool.shutdown(wait=True)
        self._write_pool.shutdown(wait=True)
        return sorted(self._completed, key=lambda item: item.output_index)

    def _vlm_backlog_count(self) -> int:
        with self._lock:
            return sum(1 for future in self._pending_vlm if not future.done())

    def _vlm_futures(self) -> list[Future[None]]:
        with self._lock:
            return list(self._pending_vlm)

    def _write_futures(self) -> list[Future[ChatWriteResult]]:
        with self._lock:
            return list(self._pending_write)

    def _wait_oldest_vlm(self) -> None:
        for future in self._vlm_futures():
            if not future.done():
                future.result()
                return

    def _run_vlm_job(self, job: PendingChatWrite) -> None:
        try:
            messages = self.driver.extract_chat_messages_from_capture(
                job.captured,
                recent_window_hours=job.recent_window_hours,
            )
            if not messages:
                with self._lock:
                    self._completed.append(
                        ChatWriteResult(
                            output_index=job.output_index,
                            chat_name=job.chat_name,
                            success=False,
                            error="no_messages_extracted",
                        )
                    )
                return
            write_future = self._write_pool.submit(
                self._run_write_job,
                PendingChatMessages(
                    output_index=job.output_index,
                    chat_name=job.chat_name,
                    messages=messages,
                ),
            )
            with self._lock:
                self._pending_write.append(write_future)
        except Exception as e:
            with self._lock:
                self._completed.append(
                    ChatWriteResult(
                        output_index=job.output_index,
                        chat_name=job.chat_name,
                        success=False,
                        error=f"{type(e).__name__}: {e}",
                    )
                )

    def _run_write_job(self, job: PendingChatMessages) -> ChatWriteResult:
        try:
            output_path = write_chat_messages_json(
                output_dir=self.output_dir,
                chat_name=job.chat_name,
                messages=job.messages,
                output_index=job.output_index,
            )
            print(
                f"[SUCCESS] Successfully saved {len(job.messages)} messages to {output_path}"
            )
            return ChatWriteResult(
                output_index=job.output_index,
                chat_name=job.chat_name,
                success=True,
                json_path=output_path,
                message_count=len(job.messages),
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


def make_async_queue(driver: Any, output_dir: str) -> AsyncChatExtractionQueue:
    worker_count = async_vlm_worker_count()
    assert can_capture_async(driver), "driver must expose capture/extract hooks for async capture"
    return AsyncChatExtractionQueue(
        driver=driver,
        output_dir=output_dir,
        max_workers=worker_count,
        max_pending=async_vlm_max_pending(worker_count),
        write_workers=async_json_worker_count(),
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
