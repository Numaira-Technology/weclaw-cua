"""run command — full pipeline: capture + report.

Usage:
    weclaw run                         # full pipeline with built-in LLM
    weclaw run --no-llm                # stepwise: capture only, output images+prompts
    weclaw run --format text           # human-readable output

In --no-llm mode, only capture runs (stepwise). Report generation is skipped
because the agent handles LLM calls externally.
"""

import click

from ..output.formatter import output


@click.command()
@click.option("--no-llm", is_flag=True, default=False,
              help="Stepwise mode: output images+prompts for agent, skip report")
@click.option("--work-dir", default=None,
              help="Work directory for stepwise output")
@click.option("--format", "fmt", default="json",
              type=click.Choice(["json", "text"]),
              help="Output format")
@click.pass_context
def run(ctx, no_llm, work_dir, fmt):
    """Run full pipeline: capture unread chats + generate report.

    \b
    Default mode:
      1. Vision-capture all unread WeChat messages (algo_a)
      2. Generate LLM triage report (algo_b)
      3. Write last_run.json for automation

    \b
    Stepwise mode (--no-llm):
      1. Vision-capture with stepwise backend (no LLM calls)
      2. Output manifest + images + prompts for agent
      3. Agent processes with own LLM, then runs `weclaw finalize`
      4. Agent builds report prompt via `weclaw build-report-prompt`
    """
    import os
    import sys

    from ..context import load_app_context

    app = load_app_context(ctx)
    config = app["config"]
    root = app["root"]
    out_dir = app["output_dir"]

    if root not in sys.path:
        sys.path.insert(0, root)

    if no_llm:
        ctx.invoke(
            capture_cmd,
            no_llm=True,
            work_dir=work_dir,
            fmt=fmt,
        )
        return

    from algo_a import run_pipeline_a
    from algo_b import run_pipeline_b
    from shared.run_manifest import build_last_run_payload, write_last_run

    err = None
    json_paths = []
    report_text = None
    try:
        json_paths = run_pipeline_a(config)
        abs_json = [os.path.abspath(p) for p in json_paths]
        if abs_json:
            report_text = run_pipeline_b(config, abs_json)
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        payload = build_last_run_payload(
            ok=False,
            config_path=app["config_path"],
            weclaw_root=root,
            output_dir=out_dir,
            message_json_paths=[],
            report_generated=False,
            error=err,
        )
        write_last_run(out_dir, payload)
        raise

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

    if fmt == "json":
        result = {
            "ok": True,
            "chats_captured": len(json_paths),
            "files": json_paths,
            "report_generated": report_text is not None,
        }
        if report_text:
            result["report"] = report_text
        output(result, "json")
    else:
        if report_text:
            output(report_text, "text")
        else:
            output("No unread messages found.", "text")


from .capture import capture as capture_cmd
