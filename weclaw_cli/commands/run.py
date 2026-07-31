"""run command — full pipeline: capture + report.

Usage:
    weclaw run                         # full pipeline with built-in LLM
    weclaw run --openclaw-gateway      # full pipeline via local OpenClaw gateway
    weclaw run --no-llm                # stepwise: capture only, output images+prompts
    weclaw run --format text           # human-readable output

In --no-llm mode, only capture runs (stepwise). Report generation is skipped
because the agent handles LLM calls externally.
"""

import click

from ..output.formatter import output


def _capture_failure_summary(failures: list[dict]) -> str | None:
    if not failures:
        return None
    rendered = [
        f"{item.get('chat_name', 'unknown')}:{item.get('stage', 'capture')}="
        f"{item.get('error', 'unknown error')}"
        for item in failures
    ]
    return "capture failures: " + "; ".join(rendered)


@click.command()
@click.option("--no-llm", is_flag=True, default=False,
              help="Stepwise mode: output images+prompts for agent, skip report")
@click.option("--openclaw-gateway", is_flag=True, default=False,
              help="Use the configured OpenClaw gateway for vision + report")
@click.option("--work-dir", default=None,
              help="Work directory for stepwise output")
@click.option("--format", "fmt", default="json",
              type=click.Choice(["json", "text"]),
              help="Output format")
@click.option("--chat-type", default=None,
              type=click.Choice(["group", "private", "all"]),
              help="Override chat type selection: group, private, or all")
@click.option("--unread-mode", default=None,
              type=click.Choice(["unread", "all"]),
              help="Override unread selection: unread badges only, or all selected chats")
@click.option("--sidebar-max-scrolls", default=None, type=int,
              help="Override max downward sidebar scrolls per scan")
@click.option("--chat-max-scrolls", default=None, type=int,
              help="Override max upward chat-panel scrolls per chat")
@click.option("--recent-window-hours", default=None, type=int,
              help="Keep only messages within this many hours (0 = no limit)")
@click.pass_context
def run(
    ctx,
    no_llm,
    openclaw_gateway,
    work_dir,
    fmt,
    chat_type,
    unread_mode,
    sidebar_max_scrolls,
    chat_max_scrolls,
    recent_window_hours,
):
    """Run full pipeline: capture selected chats + generate report.

    \b
    Default mode:
      1. Vision-capture selected WeChat messages (algo_a)
      2. Generate LLM triage report (algo_b)
      3. Write last_run.json for automation

    \b
    Stepwise mode (--no-llm):
      1. Vision-capture with stepwise backend (no LLM calls)
      2. Output manifest + images + prompts for agent
      3. Agent processes with own LLM, then runs `weclaw finalize`
      4. Agent builds report prompt via `weclaw build-report-prompt`

    \b
    OpenClaw gateway mode (--openclaw-gateway):
      1. Vision-capture selected chats with the standard pipeline
      2. Route vision prompts through the local OpenClaw gateway
      3. Generate the report via the same OpenClaw gateway
    """
    import os
    import sys

    from ..context import apply_capture_overrides, load_app_context
    from ..progress import progress_to_stderr
    from shared.capture_result import capture_failures, capture_status

    app = load_app_context(ctx)
    config = app["config"]
    apply_capture_overrides(
        config,
        chat_type=chat_type,
        unread_mode=unread_mode,
        sidebar_max_scrolls=sidebar_max_scrolls,
        chat_max_scrolls=chat_max_scrolls,
        recent_window_hours=recent_window_hours,
    )
    root = app["root"]
    out_dir = app["output_dir"]

    if root not in sys.path:
        sys.path.insert(0, root)

    if no_llm and openclaw_gateway:
        raise click.UsageError("Use either --no-llm or --openclaw-gateway, not both.")

    if no_llm:
        ctx.invoke(
            capture_cmd,
            no_llm=True,
            work_dir=work_dir,
            fmt=fmt,
            chat_type=chat_type,
            unread_mode=unread_mode,
            sidebar_max_scrolls=sidebar_max_scrolls,
            chat_max_scrolls=chat_max_scrolls,
            recent_window_hours=recent_window_hours,
        )
        return

    if openclaw_gateway:
        from algo_a import run_pipeline_a
        from shared.openclaw_gateway import (
            OpenClawGatewayConfig,
            OpenClawVisionBackend,
            gateway_chat_text,
        )
        from shared.run_manifest import build_last_run_payload, write_last_run

        from .build_report_prompt import build_prompt_from_json_paths

        err = None
        report_text = None
        json_paths = []
        failures: list[dict] = []
        status = "ok"
        try:
            gateway = OpenClawGatewayConfig.from_env_or_local()
            vision_backend = OpenClawVisionBackend(gateway)
            with progress_to_stderr():
                capture_result = run_pipeline_a(
                    config,
                    vision_backend=vision_backend,
                )
            json_paths = list(capture_result)
            failures = capture_failures(capture_result)
            status = capture_status(capture_result)
            abs_json = [os.path.abspath(p) for p in json_paths]
            if abs_json:
                custom_prompt = config.report_custom_prompt or "Summarize key decisions and action items."
                prompt_text = build_prompt_from_json_paths(abs_json, custom_prompt)
                with progress_to_stderr():
                    report_text = gateway_chat_text(
                        gateway,
                        prompt_text,
                        max_tokens=8192,
                    )
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            payload = build_last_run_payload(
                ok=False,
                config_path=app["config_path"],
                weclaw_root=root,
                output_dir=out_dir,
                message_json_paths=json_paths,
                report_generated=False,
                error=err,
            )
            write_last_run(out_dir, payload)
            raise

        err = _capture_failure_summary(failures)
        payload = build_last_run_payload(
            ok=not failures,
            config_path=app["config_path"],
            weclaw_root=root,
            output_dir=out_dir,
            message_json_paths=json_paths,
            report_generated=report_text is not None,
            error=err,
        )
        write_last_run(out_dir, payload)

        if fmt == "json":
            result = {
                "ok": not failures,
                "status": status,
                "backend": "openclaw-gateway",
                "chats_captured": len(json_paths),
                "report_generated": report_text is not None,
                "failures": failures,
            }
            if json_paths:
                result["files"] = json_paths
            if report_text:
                result["report"] = report_text
            output(result, "json")
        else:
            if report_text:
                output(report_text, "text")
            else:
                output("No matching messages found.", "text")
        if failures:
            ctx.exit(1)
        return

    from algo_a import run_pipeline_a
    from algo_b import run_pipeline_b
    from shared.run_manifest import build_last_run_payload, write_last_run

    err = None
    json_paths = []
    report_text = None
    failures: list[dict] = []
    status = "ok"
    try:
        with progress_to_stderr():
            capture_result = run_pipeline_a(config)
        json_paths = list(capture_result)
        failures = capture_failures(capture_result)
        status = capture_status(capture_result)
        abs_json = [os.path.abspath(p) for p in json_paths]
        if abs_json:
            with progress_to_stderr():
                report_text = run_pipeline_b(config, abs_json)
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        payload = build_last_run_payload(
            ok=False,
            config_path=app["config_path"],
            weclaw_root=root,
            output_dir=out_dir,
            message_json_paths=json_paths,
            report_generated=False,
            error=err,
        )
        write_last_run(out_dir, payload)
        raise

    err = _capture_failure_summary(failures)
    payload = build_last_run_payload(
        ok=not failures,
        config_path=app["config_path"],
        weclaw_root=root,
        output_dir=out_dir,
        message_json_paths=json_paths,
        report_generated=report_text is not None,
        error=err,
    )
    write_last_run(out_dir, payload)

    if fmt == "json":
        result = {
            "ok": not failures,
            "status": status,
            "chats_captured": len(json_paths),
            "files": json_paths,
            "report_generated": report_text is not None,
            "failures": failures,
        }
        if report_text:
            result["report"] = report_text
        output(result, "json")
    else:
        if report_text:
            output(report_text, "text")
        else:
            output("No matching messages found.", "text")
    if failures:
        ctx.exit(1)


from .capture import capture as capture_cmd
