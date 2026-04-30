"""WeClaw-CUA CLI entry point.

Usage:
    weclaw-cua capture               # capture selected chats via vision
    weclaw-cua report                # generate report from captured messages
    weclaw-cua run                   # capture + report (full pipeline)
    weclaw-cua sessions              # list captured message files
    weclaw-cua history "GroupName"   # show messages from a captured chat
    weclaw-cua search "keyword"      # search across captured messages
    weclaw-cua export "GroupName"    # export a chat as markdown/txt
    weclaw-cua stats "GroupName"     # message statistics

The weclaw command is an alias for weclaw-cua.
"""

import sys

import click

_VERSION = "0.2.0"


@click.group()
@click.version_option(version=_VERSION, prog_name="weclaw-cua")
@click.option("--config", "config_path", default=None,
              envvar="WECLAW_CONFIG_PATH",
              help="Path to config.json (default: auto-detect)")
@click.pass_context
def cli(ctx, config_path):
    """WeClaw-CUA — vision-based WeChat message capture & report CLI

    \b
    Quick start:
      weclaw-cua init                              # first-time setup
      weclaw-cua run                               # capture + report
      weclaw-cua capture                           # capture selected chats
      weclaw-cua report                            # generate report from captures
      weclaw-cua sessions                          # list captured chats
      weclaw-cua history "Group A" --limit 20      # view chat messages
      weclaw-cua search "deadline" --chat "Team"   # search messages
      weclaw-cua export "Group A" --format markdown # export chat
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
