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
from ..pipeline_runner import execute_run_pipeline


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
@click.pass_context
def run(ctx, no_llm, openclaw_gateway, work_dir, fmt):
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

    \b
    OpenClaw gateway mode (--openclaw-gateway):
      1. Vision-capture all unread chats with the standard pipeline
      2. Route vision prompts through the local OpenClaw gateway
      3. Generate the report via the same OpenClaw gateway
    """
    from ..context import load_app_context

    app = load_app_context(ctx)

    if no_llm and openclaw_gateway:
        raise click.UsageError("Use either --no-llm or --openclaw-gateway, not both.")

    from shared.run_manifest import build_last_run_payload, write_last_run

    try:
        result = execute_run_pipeline(
            app,
            no_llm=no_llm,
            openclaw_gateway=openclaw_gateway,
            work_dir=work_dir,
        )
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        payload = build_last_run_payload(
            ok=False,
            config_path=app["config_path"],
            weclaw_root=app["root"],
            output_dir=app["output_dir"],
            message_json_paths=[],
            report_generated=False,
            error=err,
        )
        write_last_run(app["output_dir"], payload)
        raise

    if no_llm:
        if fmt == "json":
            output(result, "json")
        else:
            output(
                f"Stepwise capture complete. Pending tasks: {result.get('pending_tasks', 0)}",
                "text",
            )
        return

    if fmt == "json":
        output(result, "json")
    else:
        report_text = result.get("report")
        if report_text:
            output(str(report_text), "text")
        else:
            output("No unread messages found.", "text")
