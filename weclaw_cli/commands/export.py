"""export command — export a captured chat as markdown or text.

Usage:
    weclaw export "Group A" --format markdown
    weclaw export "Alice" --format txt --output chat.txt
"""

import os
from datetime import datetime

import click

from ..output.formatter import output


@click.command("export")
@click.argument("chat_name")
@click.option("--format", "fmt", default="markdown",
              type=click.Choice(["markdown", "txt"]),
              help="Export format")
@click.option("--output", "output_path", default=None,
              help="Output file path (default: stdout)")
@click.option("--limit", default=500, help="Max messages to export")
@click.pass_context
def export(ctx, chat_name, fmt, output_path, limit):
    """Export a captured chat as markdown or plain text.

    \b
    Examples:
      weclaw export "Group A" --format markdown
      weclaw export "Alice" --format txt --output chat.txt
      weclaw export "Team" --limit 1000
    """
    from ..context import load_app_context
    from .history import _find_chat_file, _load_messages

    app = load_app_context(ctx)
    fpath = _find_chat_file(app["output_dir"], chat_name)
    if not fpath:
        click.echo(f"Chat not found: {chat_name}", err=True)
        ctx.exit(1)

    messages = _load_messages(fpath)[:limit]

    if not messages:
        click.echo(f"No messages in {chat_name}.", err=True)
        ctx.exit(0)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    if fmt == "markdown":
        content = _format_markdown(chat_name, now, messages)
    else:
        content = _format_txt(chat_name, now, messages)

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
            if not content.endswith("\n"):
                f.write("\n")
        click.echo(f"Exported to: {output_path} ({len(messages)} messages)", err=True)
    else:
        output(content, "text")


def _format_markdown(chat_name: str, export_time: str, messages: list[dict]) -> str:
    header = (
        f"# Chat Export: {chat_name}\n\n"
        f"**Export time:** {export_time}\n\n"
        f"**Messages:** {len(messages)}\n\n---\n\n"
    )
    lines = []
    for m in messages:
        sender = m.get("sender", "?")
        time = m.get("time", "")
        content = m.get("content", "")
        mtype = m.get("type", "text")
        ts = f"[{time}] " if time else ""
        tag = f" *[{mtype}]*" if mtype != "text" else ""
        lines.append(f"- {ts}**{sender}**{tag}: {content}")
    return header + "\n".join(lines)


def _format_txt(chat_name: str, export_time: str, messages: list[dict]) -> str:
    header = (
        f"Chat Export: {chat_name}\n"
        f"Export time: {export_time}\n"
        f"Messages: {len(messages)}\n"
        f"{'=' * 60}\n"
    )
    lines = []
    for m in messages:
        sender = m.get("sender", "?")
        time = m.get("time", "")
        content = m.get("content", "")
        mtype = m.get("type", "text")
        ts = f"[{time}] " if time else ""
        tag = f" [{mtype}]" if mtype != "text" else ""
        lines.append(f"{ts}{sender}{tag}: {content}")
    return header + "\n".join(lines)
