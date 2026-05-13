"""OpenClaw gateway helper tests.

Usage:
    python -m pytest tests/test_openclaw_gateway.py

Input spec:
    - Builds temporary stepwise manifests with fake image and prompt files.
    - Stubs gateway_chat_vision so no network calls are made.

Output spec:
    - Verifies stepwise response filling can process pending API tasks concurrently.
"""

from __future__ import annotations

import json
import os
import time

from shared.openclaw_gateway import OpenClawGatewayConfig
from shared.openclaw_gateway import fill_stepwise_responses


def _write_stepwise_task(work_dir, index: int) -> dict:
    image_name = f"step_{index}.png"
    prompt_name = f"step_{index}.prompt.txt"
    response_name = f"step_{index}.response.txt"
    (work_dir / image_name).write_bytes(b"fake image")
    (work_dir / prompt_name).write_text(f"prompt {index}", encoding="utf-8")
    return {
        "step_id": f"step_{index}",
        "image": image_name,
        "prompt_file": prompt_name,
        "response_file": response_name,
        "max_tokens": 123,
    }


def _write_manifest(work_dir, count: int) -> list[dict]:
    tasks = [_write_stepwise_task(work_dir, index) for index in range(count)]
    (work_dir / "manifest.json").write_text(
        json.dumps({"tasks": tasks}),
        encoding="utf-8",
    )
    return tasks


def test_fill_stepwise_responses_uses_workers(tmp_path, monkeypatch) -> None:
    tasks = _write_manifest(tmp_path, 3)
    calls: list[tuple[str, str, int]] = []

    def fake_gateway_chat_vision(*, config, prompt, image_path, max_tokens):
        del config
        time.sleep(0.2)
        calls.append((prompt, os.path.basename(image_path), max_tokens))
        return f"response for {prompt}"

    monkeypatch.setattr(
        "shared.openclaw_gateway.gateway_chat_vision",
        fake_gateway_chat_vision,
    )
    config = OpenClawGatewayConfig(
        base_url="http://localhost:18789/v1",
        api_key="test",
        model="openclaw/default",
    )

    started = time.perf_counter()
    result = fill_stepwise_responses(
        work_dir=str(tmp_path),
        config=config,
        workers=3,
    )
    elapsed = time.perf_counter() - started

    assert elapsed < 0.45
    assert result == {
        "total_tasks": 3,
        "responses_written": 3,
        "responses_skipped": 0,
        "workers": 3,
    }
    assert sorted(calls) == [
        ("prompt 0", "step_0.png", 123),
        ("prompt 1", "step_1.png", 123),
        ("prompt 2", "step_2.png", 123),
    ]
    for index, task in enumerate(tasks):
        response_path = tmp_path / task["response_file"]
        assert response_path.read_text(encoding="utf-8") == f"response for prompt {index}"


def test_fill_stepwise_responses_skips_existing_without_workers(tmp_path, monkeypatch) -> None:
    tasks = _write_manifest(tmp_path, 2)
    for task in tasks:
        (tmp_path / task["response_file"]).write_text("already done", encoding="utf-8")

    def fail_gateway_chat_vision(**kwargs):
        del kwargs
        raise AssertionError("gateway should not be called")

    monkeypatch.setattr(
        "shared.openclaw_gateway.gateway_chat_vision",
        fail_gateway_chat_vision,
    )
    config = OpenClawGatewayConfig(
        base_url="http://localhost:18789/v1",
        api_key="test",
        model="openclaw/default",
    )

    result = fill_stepwise_responses(
        work_dir=str(tmp_path),
        config=config,
        skip_existing=True,
        workers=3,
    )

    assert result == {
        "total_tasks": 2,
        "responses_written": 0,
        "responses_skipped": 2,
        "workers": 0,
    }
