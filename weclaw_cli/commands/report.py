"""report command — generate LLM report from captured messages.

Usage:
    weclaw report                      # report from latest capture
    weclaw report --input output/*.json  # from specific files
    weclaw report --format text        # human-readable output

Runs algo_b pipeline: loads message JSONs, builds a prompt,
and calls the configured LLM to generate a triage report.
"""

import glob
import os

import click

from ..output.formatter import output


@click.command()
@click.option("--input", "input_files", multiple=True,
              help="Message JSON file paths (default: all in output_dir)")
@click.option("--format", "fmt", default="json",
              type=click.Choice(["json", "text"]),
              help="Output format")
@click.pass_context
def report(ctx, input_files, fmt):
    """Generate an LLM report from captured message files.

    \b
    Uses the configured LLM to produce a morning triage report
    from previously captured chat messages.
    """
    from ..context import load_app_context

    app = load_app_context(ctx)
    config = app["config"]

    import sys
    if app["root"] not in sys.path:
        sys.path.insert(0, app["root"])

    from algo_b import run_pipeline_b

    if input_files:
        json_paths = list(input_files)
    else:
        json_paths = sorted(glob.glob(os.path.join(app["output_dir"], "*.json")))
        json_paths = [p for p in json_paths if not p.endswith("last_run.json")]

    if not json_paths:
        click.echo("No message files found. Run 'weclaw capture' first.", err=True)
        ctx.exit(1)

    abs_paths = [os.path.abspath(p) for p in json_paths]
    report_text = run_pipeline_b(config, abs_paths)

    if fmt == "json":
        output({
            "report": report_text,
            "source_files": json_paths,
        }, "json")
    else:
        output(report_text, "text")
