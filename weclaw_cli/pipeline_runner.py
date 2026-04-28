"""Shared pipeline executor for CLI run and local service tasks."""

from __future__ import annotations

import os
import sys
from typing import Any


def execute_run_pipeline(
    app: dict[str, Any],
    *,
    no_llm: bool = False,
    openclaw_gateway: bool = False,
    work_dir: str | None = None,
) -> dict[str, Any]:
    root = app["root"]
    if root not in sys.path:
        sys.path.insert(0, root)

    if no_llm and openclaw_gateway:
        raise ValueError("Use either no_llm or openclaw_gateway, not both.")

    if no_llm:
        from .commands.capture import run_capture_pipeline

        return run_capture_pipeline(app, no_llm=True, work_dir=work_dir)

    if openclaw_gateway:
        from algo_a import run_pipeline_a
        from shared.openclaw_gateway import (
            OpenClawGatewayConfig,
            OpenClawVisionBackend,
            gateway_chat_text,
        )
        from shared.run_manifest import build_last_run_payload, write_last_run

        from .commands.build_report_prompt import build_prompt_from_json_paths

        config = app["config"]
        out_dir = app["output_dir"]
        gateway = OpenClawGatewayConfig.from_env_or_local()
        json_paths = run_pipeline_a(config, vision_backend=OpenClawVisionBackend(gateway))
        abs_json = [os.path.abspath(p) for p in json_paths]
        report_text = None
        if abs_json:
            custom_prompt = config.report_custom_prompt or "Summarize key decisions and action items."
            prompt_text = build_prompt_from_json_paths(abs_json, custom_prompt)
            report_text = gateway_chat_text(gateway, prompt_text, max_tokens=8192)

        payload = build_last_run_payload(
            ok=True,
            config_path=app["config_path"],
            weclaw_root=root,
            output_dir=out_dir,
            message_json_paths=json_paths,
            report_generated=report_text is not None,
            error=None,
        )
        write_last_run(out_dir, payload)
        return {
            "ok": True,
            "backend": "openclaw-gateway",
            "chats_captured": len(json_paths),
            "files": json_paths,
            "report_generated": report_text is not None,
            "report": report_text,
        }

    from algo_a import run_pipeline_a
    from algo_b import run_pipeline_b
    from shared.run_manifest import build_last_run_payload, write_last_run

    config = app["config"]
    out_dir = app["output_dir"]
    json_paths = run_pipeline_a(config)
    abs_json = [os.path.abspath(p) for p in json_paths]
    report_text = run_pipeline_b(config, abs_json) if abs_json else None
    payload = build_last_run_payload(
        ok=True,
        config_path=app["config_path"],
        weclaw_root=root,
        output_dir=out_dir,
        message_json_paths=json_paths,
        report_generated=report_text is not None,
        error=None,
    )
    write_last_run(out_dir, payload)
    return {
        "ok": True,
        "chats_captured": len(json_paths),
        "files": json_paths,
        "report_generated": report_text is not None,
        "report": report_text,
    }
