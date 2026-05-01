"""report command — generate LLM report from captured messages.

Usage:
    weclaw report                        # generate report (requires API key)
    weclaw report --prompt-only          # output prompt only (no LLM call)
    weclaw report --input output/*.json  # from specific files
"""

import glob
import os

import click

from ..output.formatter import output


@click.command()
@click.option("--input", "input_files", multiple=True,
              help="Message JSON file paths (default: all in output_dir)")
@click.option("--prompt-only", is_flag=True, default=False,
              help="Output the report prompt without calling LLM")
@click.option("--format", "fmt", default="json",
              type=click.Choice(["json", "text"]),
              help="Output format")
@click.pass_context
def report(ctx, input_files, prompt_only, fmt):
    """Generate an LLM report from captured message files.

    \b
    Default mode: calls the configured LLM to generate a report.
    --prompt-only: outputs the prompt text for the agent to process.
    """
    import sys

    from ..context import load_app_context

    app = load_app_context(ctx)
    config = app["config"]

    if app["root"] not in sys.path:
        sys.path.insert(0, app["root"])

    from algo_b.load_messages import load_messages
    from algo_b.build_report_prompt import build_report_prompt

    if input_files:
        json_paths = list(input_files)
    else:
        json_paths = sorted(glob.glob(os.path.join(app["output_dir"], "*.json")))
        json_paths = [p for p in json_paths
                      if os.path.basename(p) not in ("last_run.json", "last_check.json", "manifest.json")]

    if not json_paths:
        click.echo("No message files found. Run 'weclaw capture' first.", err=True)
        ctx.exit(1)

    abs_paths = [os.path.abspath(p) for p in json_paths]
    messages = load_messages(abs_paths)
    custom_prompt = config.report_custom_prompt or "Summarize key decisions and action items."
    prompt_text = build_report_prompt(messages, custom_prompt)

    if prompt_only:
        output(prompt_text, "text")
        return

    if not config.llm_api_key:
        click.echo(
            "No API key configured. Use --prompt-only to get the prompt, "
            "or set the API key for the configured llm_provider.",
            err=True,
        )
        ctx.exit(1)

    from algo_b.generate_report import generate_report

    report_text = generate_report(
        prompt_text,
        config.llm_model,
        config.llm_api_key,
        config.llm_provider,
        config.llm_base_url,
        config.llm_wire_model,
    )

    if fmt == "json":
        output({
            "report": report_text,
            "source_files": json_paths,
        }, "json")
    else:
        output(report_text, "text")
