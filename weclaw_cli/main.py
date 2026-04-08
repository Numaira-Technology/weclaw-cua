"""weclaw CLI entry point.

Usage:
    weclaw capture                   # capture unread chats via vision
    weclaw report                    # generate report from captured messages
    weclaw run                       # capture + report (full pipeline)
    weclaw sessions                  # list captured message files
    weclaw history "GroupName"       # show messages from a captured chat
    weclaw search "keyword"          # search across captured messages
    weclaw export "GroupName"        # export a chat as markdown/txt
    weclaw stats "GroupName"         # message statistics
"""

import sys

import click

_VERSION = "0.1.0"


@click.group()
@click.version_option(version=_VERSION, prog_name="weclaw")
@click.option("--config", "config_path", default=None,
              envvar="WECLAW_CONFIG_PATH",
              help="Path to config.json (default: auto-detect)")
@click.pass_context
def cli(ctx, config_path):
    """WeClaw — vision-based WeChat message capture & report CLI

    \b
    Quick start:
      weclaw init                                  # first-time setup
      weclaw run                                   # capture + report
      weclaw capture                               # capture unread chats
      weclaw report                                # generate report from captures
      weclaw sessions                              # list captured chats
      weclaw history "Group A" --limit 20          # view chat messages
      weclaw search "deadline" --chat "Team"       # search messages
      weclaw export "Group A" --format markdown    # export chat
    """
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config_path


from .commands.init import init
from .commands.run import run
from .commands.capture import capture
from .commands.report import report
from .commands.finalize import finalize
from .commands.build_report_prompt import build_report_prompt
from .commands.sessions import sessions
from .commands.history import history
from .commands.search import search
from .commands.export import export
from .commands.stats import stats
from .commands.unread import unread
from .commands.new_messages import new_messages

cli.add_command(init)
cli.add_command(run)
cli.add_command(capture)
cli.add_command(report)
cli.add_command(finalize)
cli.add_command(build_report_prompt)
cli.add_command(sessions)
cli.add_command(history)
cli.add_command(search)
cli.add_command(export)
cli.add_command(stats)
cli.add_command(unread)
cli.add_command(new_messages)


if __name__ == "__main__":
    cli()
