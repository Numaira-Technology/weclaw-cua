"""search command — search across captured messages.

Usage:
    weclaw search "deadline"                  # global search
    weclaw search "deadline" --chat "Team"    # in specific chat
    weclaw search "report" --type text        # text messages only
"""

import json
import os

import click

from ..output.formatter import output


@click.command("search")
@click.argument("keyword")
@click.option("--chat", multiple=True, help="Limit to specific chat(s)")
@click.option("--limit", default=20, help="Max results (max 500)")
@click.option("--offset", default=0, help="Pagination offset")
@click.option("--format", "fmt", default="json",
              type=click.Choice(["json", "text"]),
              help="Output format")
@click.option("--type", "msg_type", default=None,
              type=click.Choice(["text", "system", "link_card", "image", "file", "recalled", "unsupported"]),
              help="Filter by message type")
@click.pass_context
def search(ctx, keyword, chat, limit, offset, fmt, msg_type):
    """Search messages across captured chats.

    \b
    Examples:
      weclaw search "Claude"                         # global search
      weclaw search "Claude" --chat "AI Group"       # in specific chat
      weclaw search "meeting" --chat "A" --chat "B"  # multiple chats
      weclaw search "hello" --limit 50               # more results
    """
    from ..context import load_app_context

    app = load_app_context(ctx)
    out_dir = app["output_dir"]

    if not os.path.isdir(out_dir):
        click.echo("No output directory. Run 'weclaw capture' first.", err=True)
        ctx.exit(1)

    chat_names = list(chat)
    json_files = [
        f for f in os.listdir(out_dir)
        if f.endswith(".json") and f != "last_run.json"
    ]

    if chat_names:
        lower_names = [n.lower() for n in chat_names]
        json_files = [
            f for f in json_files
            if os.path.splitext(f)[0].lower() in lower_names
            or any(n in os.path.splitext(f)[0].lower() for n in lower_names)
        ]

    kw_lower = keyword.lower()
    results = []

    for fname in json_files:
        fpath = os.path.join(out_dir, fname)
        chat_name_file = os.path.splitext(fname)[0]
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                messages = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        if not isinstance(messages, list):
            continue

        for m in messages:
            if msg_type and m.get("type") != msg_type:
                continue
            content = m.get("content", "")
            sender = m.get("sender", "")
            if kw_lower in content.lower() or kw_lower in sender.lower():
                results.append({
                    "chat": m.get("chat_name", chat_name_file),
                    "sender": sender,
                    "time": m.get("time", ""),
                    "content": content,
                    "type": m.get("type", "text"),
                })

    page = results[offset:offset + limit]
    scope = ", ".join(chat_names) if chat_names else "all chats"

    if fmt == "json":
        output({
            "scope": scope,
            "keyword": keyword,
            "count": len(page),
            "total": len(results),
            "offset": offset,
            "limit": limit,
            "type": msg_type,
            "results": page,
        }, "json")
    else:
        if not page:
            output(f'No results for "{keyword}" in {scope}.', "text")
            return
        lines = [f'Search "{keyword}" in {scope} ({len(page)}/{len(results)} results):']
        for r in page:
            ts = f"[{r['time']}] " if r["time"] else ""
            lines.append(f"  {ts}{r['chat']} / {r['sender']}: {r['content']}")
        output("\n".join(lines), "text")
