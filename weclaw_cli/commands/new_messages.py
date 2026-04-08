"""new-messages command — incremental new messages since last check.

Usage:
    weclaw new-messages                # first call: capture + save state
    weclaw new-messages                # subsequent: only new since last

State saved at output_dir/last_check.json. Delete to reset.
"""

import json
import os
from datetime import datetime

import click

from ..output.formatter import output


@click.command("new-messages")
@click.option("--format", "fmt", default="json",
              type=click.Choice(["json", "text"]),
              help="Output format")
@click.pass_context
def new_messages(ctx, fmt):
    """Get messages captured since the last check.

    \b
    First call: returns all captured messages and saves state.
    Subsequent calls: returns only new/updated chats since last check.
    State file: <output_dir>/last_check.json (delete to reset).
    """
    from ..context import load_app_context

    app = load_app_context(ctx)
    out_dir = app["output_dir"]
    state_file = os.path.join(out_dir, "last_check.json")

    if not os.path.isdir(out_dir):
        click.echo("No output directory. Run 'weclaw capture' first.", err=True)
        ctx.exit(1)

    json_files = {
        f: os.path.getmtime(os.path.join(out_dir, f))
        for f in os.listdir(out_dir)
        if f.endswith(".json") and f not in ("last_run.json", "last_check.json")
    }

    last_state = {}
    if os.path.isfile(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                last_state = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    new_state = {fname: mtime for fname, mtime in json_files.items()}

    if not last_state:
        _save_state(state_file, new_state)
        results = []
        for fname, mtime in sorted(json_files.items(), key=lambda x: x[1], reverse=True):
            chat_name = os.path.splitext(fname)[0]
            results.append({
                "chat": chat_name,
                "file": fname,
                "time": datetime.fromtimestamp(mtime).strftime("%H:%M"),
            })

        if fmt == "json":
            output({"first_call": True, "count": len(results), "chats": results}, "json")
        else:
            if results:
                lines = [f"Current captured chats ({len(results)}):"]
                for r in results:
                    lines.append(f"  [{r['time']}] {r['chat']}")
                output("\n".join(lines), "text")
            else:
                output("No captured chats (state saved, next call will detect new ones).", "text")
        return

    new_chats = []
    for fname, mtime in json_files.items():
        prev_mtime = last_state.get(fname, 0)
        if mtime > prev_mtime:
            chat_name = os.path.splitext(fname)[0]
            new_chats.append({
                "chat": chat_name,
                "file": fname,
                "time": datetime.fromtimestamp(mtime).strftime("%H:%M:%S"),
            })

    _save_state(state_file, new_state)

    if fmt == "json":
        output({"first_call": False, "new_count": len(new_chats), "chats": new_chats}, "json")
    else:
        if not new_chats:
            output("No new messages since last check.", "text")
        else:
            lines = [f"{len(new_chats)} new/updated chat(s):"]
            for c in new_chats:
                lines.append(f"  [{c['time']}] {c['chat']}")
            output("\n".join(lines), "text")


def _save_state(state_file: str, state: dict) -> None:
    os.makedirs(os.path.dirname(state_file), exist_ok=True)
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f)
