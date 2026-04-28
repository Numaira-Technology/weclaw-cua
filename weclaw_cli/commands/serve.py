"""serve command — keep-alive local HTTP service for desktop app integration."""

from __future__ import annotations

import click

from ..context import load_app_context
from ..service_runtime import run_keep_alive_server


@click.command("serve")
@click.option("--host", default="127.0.0.1", show_default=True, help="Bind host")
@click.option("--port", default=8765, show_default=True, type=int, help="Bind port")
@click.pass_context
def serve(ctx, host: str, port: int) -> None:
    """Run a local keep-alive task service for app-to-CUA integration."""
    app = load_app_context(ctx)
    run_keep_alive_server(app, host=host, port=port)
