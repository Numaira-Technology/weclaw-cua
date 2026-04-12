"""history command — view messages from a captured chat.

Usage:
    weclaw history "Group A"              # last 50 messages
    weclaw history "Group A" --limit 100  # last 100
    weclaw history "Alice" --format text  # human-readable
"""

import json
import os

import click

from ..output.formatter import output


def _find_chat_file(out_dir: str, chat_name: str) -> str | None:
    """Find a chat JSON file by name (case-insensitive fuzzy match)."""
    exact = os.path.join(out_dir, f"{chat_name}.json")
    if os.path.isfile(exact):
        return exact
    lower = chat_name.lower()
    for fname in os.listdir(out_dir):
        if fname.endswith(".json") and fname != "last_run.json":
            if os.path.splitext(fname)[0].lower() == lower:
                return os.path.join(out_dir, fname)
    for fname in os.listdir(out_dir):
        if fname.endswith(".json") and fname != "last_run.json":
            if lower in os.path.splitext(fname)[0].lower():
                return os.path.join(out_dir, fname)
    return None


def _load_messages(fpath: str) -> list[dict]:
    with open(fpath, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, list), f"Expected list in {fpath}"
    return data


@click.command("history")
@click.argument("chat_name")
@click.option("--limit", default=50, help="Number of messages to return")
@click.option("--offset", default=0, help="Pagination offset")
@click.option("--format", "fmt", default="json",
              type=click.Choice(["json", "text"]),
              help="Output format")
@click.option("--type", "msg_type", default=None,
              type=click.Choice(["text", "system", "link_card", "image", "file", "recalled", "unsupported"]),
              help="Filter by message type")
@click.pass_context
def history(ctx, chat_name, limit, offset, fmt, msg_type):
    """View messages from a captured chat.

    \b
    Examples:
      weclaw history "Group A"                          # last 50 messages
      weclaw history "Group A" --limit 100 --offset 50  # pagination
      weclaw history "Alice" --type text --format text  # text messages only
    """
    from ..context import load_app_context

    app = load_app_context(ctx)
    fpath = _find_chat_file(app["output_dir"], chat_name)
    if not fpath:
        click.echo(f"Chat not found: {chat_name}", err=True)
        click.echo("Run 'weclaw sessions' to see available chats.", err=True)
        ctx.exit(1)

    messages = _load_messages(fpath)

    if msg_type:
        messages = [m for m in messages if m.get("type") == msg_type]

    page = messages[offset:offset + limit]

    if fmt == "json":
        output({
            "chat": chat_name,
            "count": len(page),
            "total": len(messages),
            "offset": offset,
            "limit": limit,
            "type": msg_type,
            "messages": page,
        }, "json")
    else:
        if not page:
            output(f"No messages found for {chat_name}.", "text")
            return
        lines = [f"{chat_name} ({len(page)}/{len(messages)} messages, offset={offset}):"]
        for m in page:
            sender = m.get("sender", "?")
            time = m.get("time", "")
            content = m.get("content", "")
            mtype = m.get("type", "text")
            ts = f"[{time}] " if time else ""
            tag = f" [{mtype}]" if mtype != "text" else ""
            lines.append(f"  {ts}{sender}{tag}: {content}")
        output("\n".join(lines), "text")
