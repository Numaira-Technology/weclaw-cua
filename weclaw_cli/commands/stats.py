"""stats command — message statistics for a captured chat.

Usage:
    weclaw stats "Group A"              # JSON stats
    weclaw stats "Group A" --format text  # human-readable
"""

import json
import os
from collections import Counter

import click

from ..output.formatter import output


@click.command("stats")
@click.argument("chat_name")
@click.option("--format", "fmt", default="json",
              type=click.Choice(["json", "text"]),
              help="Output format")
@click.pass_context
def stats(ctx, chat_name, fmt):
    """Show statistics for a captured chat.

    \b
    Examples:
      weclaw stats "Group A"
      weclaw stats "Alice" --format text
    """
    from ..context import load_app_context
    from .history import _find_chat_file, _load_messages

    app = load_app_context(ctx)
    fpath = _find_chat_file(app["output_dir"], chat_name)
    if not fpath:
        click.echo(f"Chat not found: {chat_name}", err=True)
        ctx.exit(1)

    messages = _load_messages(fpath)
    total = len(messages)
    type_counter = Counter(m.get("type", "text") for m in messages)
    sender_counter = Counter(m.get("sender", "?") for m in messages)
    top_senders = [
        {"name": name, "count": count}
        for name, count in sender_counter.most_common(10)
    ]

    result = {
        "chat": chat_name,
        "total": total,
        "type_breakdown": dict(type_counter),
        "top_senders": top_senders,
    }

    if fmt == "json":
        output(result, "json")
    else:
        lines = [f"{chat_name} Statistics"]
        lines.append(f"Total messages: {total}")
        lines.append("\nMessage types:")
        for t, cnt in type_counter.most_common():
            pct = cnt / total * 100 if total > 0 else 0
            lines.append(f"  {t}: {cnt} ({pct:.1f}%)")
        if top_senders:
            lines.append("\nTop senders:")
            for s in top_senders:
                lines.append(f"  {s['name']}: {s['count']}")
        output("\n".join(lines), "text")
