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
    """Find the project root directory.

    Priority:
      1. WECLAW_ROOT env var (explicit override)
      2. Walk up from cwd looking for pyproject.toml or config/
      3. cwd itself as fallback
    """
    env_root = os.environ.get("WECLAW_ROOT", "").strip()
    if env_root and os.path.isdir(env_root):
        return os.path.abspath(env_root)

    cwd = os.getcwd()
    candidate = cwd
    for _ in range(10):
        if os.path.isfile(os.path.join(candidate, "pyproject.toml")):
            return candidate
        if os.path.isdir(os.path.join(candidate, "config")):
            return candidate
        parent = os.path.dirname(candidate)
        if parent == candidate:
            break
        candidate = parent

    return cwd


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
