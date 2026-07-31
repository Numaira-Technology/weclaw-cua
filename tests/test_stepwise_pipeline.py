import json
from types import SimpleNamespace

from PIL import Image

from algo_a.pipeline_a_stepwise import StepwiseCaptureQueue, run_pipeline_a_stepwise
from config.weclaw_config import WeclawConfig
from shared.capture_result import CaptureRunResult
from shared.datatypes import CapturedChatImages, ChatImageChunk
from shared.stepwise_backend import StepwiseBackend


class FakeStepwiseDriver:
    def capture_chat_messages(
        self,
        chat_name: str,
        *,
        max_messages=None,
        max_scrolls=None,
        skip_navigation_vlm=False,
    ) -> CapturedChatImages:
        del max_messages, max_scrolls, skip_navigation_vlm
        return CapturedChatImages(
            chat_name=chat_name,
            chunks=[
                ChatImageChunk(
                    chunk_index=0,
                    chunk_total=1,
                    image=Image.new("RGB", (10, 10), "white"),
                )
            ],
        )


def _config(output_dir: str) -> WeclawConfig:
    return WeclawConfig(
        wechat_app_name="WeChat",
        groups_to_monitor=["Chat A", "Chat B"],
        sidebar_unread_only=False,
        chat_type="all",
        sidebar_max_scrolls=0,
        chat_max_scrolls=0,
        report_custom_prompt="Summarize.",
        openrouter_api_key="",
        llm_model="openai/gpt-4o",
        output_dir=output_dir,
    )


def test_stepwise_queue_emits_tasks_for_multiple_selected_chats(tmp_path) -> None:
    backend = StepwiseBackend(
        str(tmp_path),
        record_untyped_queries=False,
    )
    queue = StepwiseCaptureQueue(driver=FakeStepwiseDriver(), backend=backend)

    assert queue.capture_and_submit("Chat A", output_index=1)
    assert queue.capture_and_submit("Chat B", output_index=2)
    results = queue.drain()

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert [result.chat_name for result in results] == ["Chat A", "Chat B"]
    assert manifest["metadata"]["captured_chats"] == ["Chat A", "Chat B"]
    assert [
        task["metadata"]["chat_name"] for task in manifest["tasks"]
    ] == ["Chat A", "Chat B"]
    assert all(
        task["metadata"]["kind"] == "message_extraction"
        for task in manifest["tasks"]
    )


def test_new_stepwise_run_replaces_manifest_without_reusing_responses(tmp_path) -> None:
    first = StepwiseBackend(str(tmp_path))
    first.query("first", Image.new("RGB", (10, 10), "white"))
    first_task = first.get_pending_tasks()[0]
    (tmp_path / first_task["response_file"]).write_text("stale", encoding="utf-8")

    second = StepwiseBackend(str(tmp_path))
    second.query("second", Image.new("RGB", (10, 10), "white"))
    second_task = second.get_pending_tasks()[0]
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))

    assert first.run_id != second.run_id
    assert len(manifest["tasks"]) == 1
    assert second_task["step_id"] != first_task["step_id"]
    assert not (tmp_path / second_task["response_file"]).exists()


def test_stepwise_pipeline_requests_ocr_navigation_and_multi_chat_queue(
    monkeypatch,
    tmp_path,
) -> None:
    backend = StepwiseBackend(
        str(tmp_path),
        record_untyped_queries=False,
    )
    config = _config(str(tmp_path / "output"))
    observed = {}

    def fake_sidebar_pipeline(
        received_config,
        vision_backend=None,
        *,
        extraction_queue_factory=None,
        prefer_ocr_navigation=False,
    ):
        observed["config"] = received_config
        observed["backend"] = vision_backend
        observed["prefer_ocr_navigation"] = prefer_ocr_navigation
        queue = extraction_queue_factory(FakeStepwiseDriver(), received_config.output_dir)
        queue.capture_and_submit("Chat A", output_index=1)
        queue.capture_and_submit("Chat B", output_index=2)
        queue.drain()
        return CaptureRunResult()

    monkeypatch.setattr(
        "algo_a.pipeline_a_win._run_sidebar_scan_pipeline",
        fake_sidebar_pipeline,
    )

    run_pipeline_a_stepwise(config, backend)

    assert observed["config"] is config
    assert observed["backend"] is backend
    assert observed["prefer_ocr_navigation"] is True
    assert backend.get_message_chat_names() == ["Chat A", "Chat B"]
