"""Stepwise multi-chat capture using local OCR navigation and deferred extraction."""

from __future__ import annotations

import os
import sys
from typing import Any

from algo_a.async_chat_extraction import ChatWriteResult
from config.weclaw_config import WeclawConfig
from shared.capture_result import CaptureRunResult
from shared.stepwise_backend import StepwiseBackend
from shared.vision_prompts import CHAT_PANEL_PROMPT


class StepwiseCaptureQueue:
    """Capture selected chats synchronously and emit one manifest task per image chunk."""

    def __init__(self, *, driver: Any, backend: StepwiseBackend) -> None:
        self.driver = driver
        self.backend = backend
        self._results: list[ChatWriteResult] = []

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
        chunks = list(getattr(captured, "chunks", None) or [])
        display_name = str(persist_chat_name or chat_name).strip() or chat_name
        if not chunks:
            self._results.append(
                ChatWriteResult(
                    output_index=output_index,
                    chat_name=display_name,
                    success=False,
                    error="no_screenshots_captured",
                )
            )
            return False

        for chunk in sorted(chunks, key=lambda item: item.chunk_index):
            self.backend.query(
                CHAT_PANEL_PROMPT,
                chunk.image,
                max_tokens=16384,
                task_metadata={
                    "kind": "message_extraction",
                    "chat_name": display_name,
                    "capture_chat_name": chat_name,
                    "chunk_index": chunk.chunk_index,
                    "chunk_total": chunk.chunk_total,
                    "recent_window_hours": recent_window_hours,
                },
            )

        self._results.append(
            ChatWriteResult(
                output_index=output_index,
                chat_name=display_name,
                success=True,
                message_count=len(chunks),
            )
        )
        return True

    def drain(self) -> list[ChatWriteResult]:
        self.backend.set_metadata(
            {"captured_chats": self.backend.get_message_chat_names()}
        )
        return sorted(self._results, key=lambda item: item.output_index)


def run_pipeline_a_stepwise(
    config: WeclawConfig,
    backend: StepwiseBackend,
) -> CaptureRunResult:
    """Navigate configured chats with OCR and write extraction tasks without LLM calls."""
    assert backend is not None
    os.makedirs(config.output_dir, exist_ok=True)

    if sys.platform not in ("darwin", "win32"):
        raise NotImplementedError(f"Platform {sys.platform} not supported")

    from algo_a.pipeline_a_win import _run_sidebar_scan_pipeline

    def queue_factory(driver, _output_dir):
        return StepwiseCaptureQueue(driver=driver, backend=backend)

    return _run_sidebar_scan_pipeline(
        config,
        vision_backend=backend,
        extraction_queue_factory=queue_factory,
        prefer_ocr_navigation=True,
    )
