"""sessions command — list captured chat files.

Usage:
    weclaw sessions                    # list all captured chats (JSON)
    weclaw sessions --limit 10         # limit results
    weclaw sessions --format text      # human-readable output

Lists message JSON files from the output directory,
showing chat name, message count, and last capture time.
"""

import json
import os
from datetime import datetime

import click

from ..output.formatter import output


@click.command("sessions")
@click.option("--limit", default=20, help="Number of sessions to return")
@click.option("--format", "fmt", default="json",
              type=click.Choice(["json", "text"]),
              help="Output format")
@click.pass_context
def sessions(ctx, limit, fmt):
    """List captured chat sessions.

    \b
    Examples:
      weclaw sessions                 # all captured chats (JSON)
      weclaw sessions --limit 10      # last 10
      weclaw sessions --format text   # human-readable
    """
    from ..context import load_app_context

    app = load_app_context(ctx)
    out_dir = app["output_dir"]

    if not os.path.isdir(out_dir):
        click.echo("No output directory found. Run 'weclaw capture' first.", err=True)
        ctx.exit(1)

    json_files = sorted(
        [f for f in os.listdir(out_dir) if f.endswith(".json") and f != "last_run.json"],
        key=lambda f: os.path.getmtime(os.path.join(out_dir, f)),
        reverse=True,
    )[:limit]

    results = []
    for fname in json_files:
        fpath = os.path.join(out_dir, fname)
        mtime = os.path.getmtime(fpath)
        chat_name = os.path.splitext(fname)[0]
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                messages = json.load(f)
            msg_count = len(messages) if isinstance(messages, list) else 0
        except (json.JSONDecodeError, OSError):
            msg_count = 0

        results.append({
            "chat": chat_name,
            "file": fname,
            "messages": msg_count,
            "captured_at": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M"),
        })

    if fmt == "json":
        output(results, "json")
    else:
        if not results:
            output("No captured chats found.", "text")
            return
        lines = [f"Captured chats ({len(results)}):"]
        for r in results:
            lines.append(f"  [{r['captured_at']}] {r['chat']} ({r['messages']} messages)")
        output("\n".join(lines), "text")
