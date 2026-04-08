"""capture command — vision-based WeChat message capture.

Usage:
    weclaw capture                     # capture all configured chats
    weclaw capture --format json       # JSON output (default)
    weclaw capture --format text       # human-readable output

Runs algo_a pipeline: finds unread chats via vision, scrolls through
message panels, captures screenshots, stitches into long images,
and extracts messages via vision LLM.

Output: JSON files in the configured output_dir.
"""

import click

from ..output.formatter import output


@click.command()
@click.option("--format", "fmt", default="json",
              type=click.Choice(["json", "text"]),
              help="Output format")
@click.pass_context
def capture(ctx, fmt):
    """Capture unread WeChat messages via vision AI.

    \b
    This command:
      1. Finds WeChat window on screen
      2. Scans sidebar for unread chats (vision-based)
      3. Clicks into each chat, scrolls, captures screenshots
      4. Stitches screenshots into long images
      5. Sends to vision LLM for message extraction
      6. Saves structured JSON to output directory
    """
    from ..context import load_app_context

    app = load_app_context(ctx)
    config = app["config"]

    import sys
    if app["root"] not in sys.path:
        sys.path.insert(0, app["root"])

    from algo_a import run_pipeline_a

    json_paths = run_pipeline_a(config)

    result = {
        "ok": True,
        "chats_captured": len(json_paths),
        "files": json_paths,
    }

    if fmt == "json":
        output(result, "json")
    else:
        if json_paths:
            lines = [f"Captured {len(json_paths)} chat(s):"]
            for p in json_paths:
                lines.append(f"  {p}")
            output("\n".join(lines), "text")
        else:
            output("No unread chats found.", "text")
