import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

from click.testing import CliRunner
from PIL import Image, ImageDraw

import algo_a
import algo_b
from config.weclaw_config import WeclawConfig
from shared.capture_result import CaptureRunResult
from shared.vision_ai import VisionAI
from weclaw_cli.commands.capture import capture
from weclaw_cli.commands.run import run
from weclaw_cli.context import load_app_context


def _config(output_dir: str) -> WeclawConfig:
    return WeclawConfig(
        wechat_app_name="WeChat",
        groups_to_monitor=["*"],
        sidebar_unread_only=False,
        chat_type="all",
        sidebar_max_scrolls=0,
        chat_max_scrolls=0,
        report_custom_prompt="Summarize.",
        openrouter_api_key="test-key",
        llm_model="openai/gpt-4o",
        output_dir=output_dir,
    )


def _load_win_driver_module(monkeypatch):
    win32com = ModuleType("win32com")
    win32com.client = ModuleType("win32com.client")
    monkeypatch.setitem(sys.modules, "win32gui", ModuleType("win32gui"))
    monkeypatch.setitem(sys.modules, "win32con", ModuleType("win32con"))
    monkeypatch.setitem(sys.modules, "win32process", ModuleType("win32process"))
    monkeypatch.setitem(sys.modules, "win32com", win32com)
    monkeypatch.setitem(sys.modules, "win32com.client", win32com.client)

    import platform_win.driver as driver_module

    return driver_module


def test_app_context_resolves_pipeline_output_dir_once(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "wechat_app_name": "WeChat",
                "groups_to_monitor": ["*"],
                "llm_model": "openai/gpt-4o",
                "output_dir": "relative-output",
            }
        ),
        encoding="utf-8",
    )
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(repo_root / "docs")

    app = load_app_context(SimpleNamespace(obj={"config_path": str(config_path)}))

    assert app["config"].output_dir == app["output_dir"]
    assert app["output_dir"] == str((repo_root / "relative-output").resolve())


def test_vision_ai_uses_resolved_config_object(monkeypatch, tmp_path) -> None:
    calls = []

    class FakeOpenAI:
        def __init__(self, **kwargs) -> None:
            calls.append(kwargs)

    monkeypatch.setattr("shared.vision_ai.OpenAI", FakeOpenAI)
    config = _config(str(tmp_path))

    ai = VisionAI(config=config)

    assert ai.provider == "openrouter"
    assert ai.model_name == "openai/gpt-4o"
    assert calls[0]["api_key"] == "test-key"
    assert "openrouter.ai" in calls[0]["base_url"]


def test_windows_driver_permission_check_is_executable(monkeypatch) -> None:
    driver_module = _load_win_driver_module(monkeypatch)
    from platform_win import grant_permissions

    calls = []
    monkeypatch.setattr(
        grant_permissions, "check_prerequisites", lambda: calls.append("checked")
    )
    driver = object.__new__(driver_module.WinDriver)

    driver.ensure_permissions()

    assert calls == ["checked"]


def test_windows_ocr_rows_detect_red_unread_badges(monkeypatch) -> None:
    driver_module = _load_win_driver_module(monkeypatch)
    unread_row = Image.new("RGB", (200, 60), "white")
    ImageDraw.Draw(unread_row).ellipse((20, 10, 38, 28), fill=(245, 55, 60))

    assert driver_module._row_has_red_unread_badge(unread_row)
    assert not driver_module._row_has_red_unread_badge(
        Image.new("RGB", (200, 60), "white")
    )


def test_capture_json_stdout_is_clean_and_partial_failure_is_nonzero(
    monkeypatch,
    tmp_path,
) -> None:
    config = _config(str(tmp_path))
    app = {
        "config": config,
        "config_path": str(tmp_path / "config.json"),
        "root": str(tmp_path),
        "output_dir": str(tmp_path),
    }
    monkeypatch.setattr(
        "weclaw_cli.context.load_app_context",
        lambda _ctx: app,
    )
    monkeypatch.setattr(
        "weclaw_cli.context.apply_capture_overrides",
        lambda loaded, **_kwargs: loaded,
    )

    def fake_run_pipeline(_config):
        print("pipeline progress must be stderr")
        result = CaptureRunResult(["ok.json"])
        result.add_failure("Broken Chat", "model response invalid", stage="extraction")
        return result

    monkeypatch.setattr(algo_a, "run_pipeline_a", fake_run_pipeline)

    result = CliRunner(mix_stderr=False).invoke(
        capture, ["--format", "json"], obj={}
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["status"] == "partial"
    assert payload["files"] == ["ok.json"]
    assert payload["failures"][0]["chat_name"] == "Broken Chat"
    assert "pipeline progress must be stderr" not in result.stdout
    assert "pipeline progress must be stderr" in result.stderr


def test_run_records_partial_capture_as_failed_last_run(monkeypatch, tmp_path) -> None:
    config = _config(str(tmp_path))
    app = {
        "config": config,
        "config_path": str(tmp_path / "config.json"),
        "root": str(tmp_path),
        "output_dir": str(tmp_path),
    }
    monkeypatch.setattr(
        "weclaw_cli.context.load_app_context",
        lambda _ctx: app,
    )
    monkeypatch.setattr(
        "weclaw_cli.context.apply_capture_overrides",
        lambda loaded, **_kwargs: loaded,
    )

    capture_result = CaptureRunResult([str(tmp_path / "ok.json")])
    capture_result.add_failure(
        "Broken Chat", "model response invalid", stage="extraction"
    )
    monkeypatch.setattr(algo_a, "run_pipeline_a", lambda _config: capture_result)
    monkeypatch.setattr(algo_b, "run_pipeline_b", lambda _config, _paths: "report")

    result = CliRunner(mix_stderr=False).invoke(
        run, ["--format", "json"], obj={}
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    last_run = json.loads((tmp_path / "last_run.json").read_text(encoding="utf-8"))
    assert payload["ok"] is False
    assert payload["status"] == "partial"
    assert last_run["ok"] is False
    assert last_run["message_json_paths"] == [str(tmp_path / "ok.json")]
    assert "Broken Chat:extraction=model response invalid" in last_run["error"]
