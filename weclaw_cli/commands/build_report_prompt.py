"""build-report-prompt command — output the LLM prompt for report generation.

Usage:
    weclaw build-report-prompt                     # from latest captures
    weclaw build-report-prompt --input file.json   # from specific files

Outputs the full text prompt that should be sent to an LLM for report generation.
The calling agent sends this to its own LLM and gets the report directly.
"""

import glob
import os

import click

from ..output.formatter import output


@click.command("build-report-prompt")
@click.option("--input", "input_files", multiple=True,
              help="Message JSON file paths (default: all in output_dir)")
@click.pass_context
def build_report_prompt(ctx, input_files):
    """Output the LLM prompt for report generation.

    \b
    For stepwise/no-LLM mode: the agent calls this to get the
    report prompt text, sends it to its own LLM, and gets the
    report directly without WeClaw needing an API key.
    """
    import sys

    from ..context import load_app_context

    app = load_app_context(ctx)
    config = app["config"]

    if app["root"] not in sys.path:
        sys.path.insert(0, app["root"])

    from algo_b.load_messages import load_messages
    from algo_b.build_report_prompt import build_report_prompt as build_prompt

    if input_files:
        json_paths = list(input_files)
    else:
        json_paths = sorted(glob.glob(os.path.join(app["output_dir"], "*.json")))
        json_paths = [p for p in json_paths
                      if not os.path.basename(p) in ("last_run.json", "last_check.json", "manifest.json")]

    if not json_paths:
        click.echo("No message files found. Run 'weclaw capture' first.", err=True)
        ctx.exit(1)

    abs_paths = [os.path.abspath(p) for p in json_paths]
    messages = load_messages(abs_paths)

    custom_prompt = config.report_custom_prompt or "Summarize key decisions and action items."
    prompt_text = build_prompt(messages, custom_prompt)

    output(prompt_text, "text")
