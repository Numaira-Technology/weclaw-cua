"""unread command — show chats with unread messages (vision scan).

Usage:
    weclaw unread                      # scan sidebar for unreads
    weclaw unread --format text        # human-readable output

Uses vision AI to scan the WeChat sidebar and identify
chats with unread badges.
"""

import click

from ..output.formatter import output


@click.command("unread")
@click.option("--limit", default=50, help="Max sessions to return")
@click.option("--format", "fmt", default="json",
              type=click.Choice(["json", "text"]),
              help="Output format")
@click.pass_context
def unread(ctx, limit, fmt):
    """Scan WeChat sidebar for unread chats via vision AI.

    \b
    Examples:
      weclaw unread                    # all unread chats
      weclaw unread --limit 10         # at most 10
      weclaw unread --format text      # human-readable
    """
    import platform as _pf
    import sys

    from ..context import load_app_context

    app = load_app_context(ctx)
    config = app["config"]

    if app["root"] not in sys.path:
        sys.path.insert(0, app["root"])

    system = _pf.system()
    if system == "Darwin":
        from platform_mac import create_driver
    elif system == "Windows":
        from platform_win import create_driver
    else:
        click.echo(f"Unsupported platform: {system}", err=True)
        ctx.exit(1)

    driver = create_driver()
    driver.ensure_permissions()
    window = driver.find_wechat_window(config.wechat_app_name)

    from algo_a.list_unread_chats import list_unread_chats
    rows = list_unread_chats(driver, window)

    results = [
        {
            "chat": driver.get_row_name(row),
            "unread": driver.get_row_badge_text(row) or "dot",
        }
        for row in rows[:limit]
    ]

    if fmt == "json":
        output(results, "json")
    else:
        if not results:
            output("No unread chats.", "text")
            return
        lines = [f"Unread chats ({len(results)}):"]
        for r in results:
            badge = f" ({r['unread']})" if r["unread"] != "dot" else " (muted)"
            lines.append(f"  {r['chat']}{badge}")
        output("\n".join(lines), "text")
