"""Shared CLI context: config loading and output dir resolution.

Usage:
    app = load_app_context(ctx)
    config = app["config"]
    output_dir = app["output_dir"]
"""

import os
import sys

import click


def _find_repo_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, ".."))


def load_app_context(ctx) -> dict:
    """Load WeclawConfig from CLI context, return dict with config + paths."""
    root = _find_repo_root()
    if root not in sys.path:
        sys.path.insert(0, root)

    from config import load_config

    config_path = ctx.obj.get("config_path")
    if not config_path:
        config_path = os.environ.get("WECLAW_CONFIG_PATH", "").strip()
    if not config_path:
        candidate = os.path.join(root, "config", "config.json")
        if os.path.isfile(candidate):
            config_path = candidate
    if not config_path:
        click.echo("No config found. Run 'weclaw init' first or set WECLAW_CONFIG_PATH.", err=True)
        sys.exit(1)

    config = load_config(config_path)
    out_dir = config.output_dir
    if not os.path.isabs(out_dir):
        out_dir = os.path.normpath(os.path.join(root, out_dir))

    return {
        "config": config,
        "config_path": config_path,
        "root": root,
        "output_dir": out_dir,
    }
