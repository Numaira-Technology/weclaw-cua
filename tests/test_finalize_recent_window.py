import json

from PIL import Image

from shared.stepwise_backend import StepwiseBackend
from weclaw_cli.commands.finalize import finalize_work_dir


def test_stepwise_backend_persists_recent_window_metadata(tmp_path) -> None:
    backend = StepwiseBackend(str(tmp_path))
    backend.set_metadata({"recent_window_hours": 24})
    backend.query("prompt", Image.new("RGB", (10, 10)), max_tokens=16)

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["metadata"]["recent_window_hours"] == 24


def test_finalize_applies_manifest_recent_window(tmp_path) -> None:
    work_dir = tmp_path / "work"
    out_dir = tmp_path / "out"
    work_dir.mkdir()
    response = {
        "chat_name": "Chat",
        "messages": [
            {"sender": "Alice", "content": "old", "time": "2000年1月1日 00:00", "type": "text"},
            {"sender": "Bob", "content": "future", "time": "2999年1月1日 00:00", "type": "text"},
        ],
    }
    (work_dir / "step_0000.response.txt").write_text(
        json.dumps(response),
        encoding="utf-8",
    )
    (work_dir / "manifest.json").write_text(
        json.dumps(
            {
                "metadata": {"recent_window_hours": 24},
                "tasks": [
                    {
                        "step_id": "step_0000",
                        "response_file": "step_0000.response.txt",
                        "completed": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = finalize_work_dir(str(work_dir), str(out_dir))
    finalized = json.loads((out_dir / "finalized_messages.json").read_text(encoding="utf-8"))

    assert result["messages_before_recent_window"] == 2
    assert result["messages_extracted"] == 1
    assert result["recent_window_hours"] == 24
    assert [msg["content"] for msg in finalized] == ["future"]
