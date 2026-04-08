"""run command — full pipeline: capture + report.

Usage:
    weclaw run                         # full pipeline
    weclaw run --format text           # human-readable output

Equivalent to running 'weclaw capture' then 'weclaw report'.
Also writes last_run.json for automation/cron integration.
"""

import click

from ..output.formatter import output


@click.command()
@click.option("--format", "fmt", default="json",
              type=click.Choice(["json", "text"]),
              help="Output format")
@click.pass_context
def run(ctx, fmt):
    """Run full pipeline: capture unread chats + generate report.

    \b
    Steps:
      1. Vision-capture all unread WeChat messages (algo_a)
      2. Generate LLM triage report from captures (algo_b)
      3. Write last_run.json for automation
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
