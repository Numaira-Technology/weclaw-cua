"""init command — interactive first-time setup.

Usage:
    weclaw init
    weclaw init --config-dir /path/to/config

Creates config/config.json from the example template if it doesn't exist,
and verifies platform prerequisites (Accessibility on macOS, etc.).
"""

import json
import os
import shutil
import sys

import click


@click.command()
@click.option("--config-dir", default=None,
              help="Directory for config.json (default: <repo>/config/)")
@click.option("--force", is_flag=True,
              help="Overwrite existing config.json")
def init(config_dir, force):
    """First-time setup: create config and verify permissions."""
    from weclaw_cli.context import _find_repo_root

    root = _find_repo_root()
    if root not in sys.path:
        sys.path.insert(0, root)

    if config_dir is None:
        config_dir = os.path.join(root, "config")

    config_path = os.path.join(config_dir, "config.json")
    example_path = os.path.join(config_dir, "config.json.example")

    click.echo("WeClaw Setup")
    click.echo("=" * 40)

    if os.path.exists(config_path) and not force:
        click.echo(f"Config already exists: {config_path}")
        click.echo("Use --force to overwrite.")
    else:
        if os.path.exists(example_path):
            shutil.copy2(example_path, config_path)
            click.echo(f"[+] Created config: {config_path}")
            click.echo("    Edit this file to set your LLM API key and groups_to_monitor.")
        else:
            os.makedirs(config_dir, exist_ok=True)
            template = {
                "wechat_app_name": "WeChat",
                "groups_to_monitor": ["*"],
                "sidebar_unread_only": True,
                "chat_type": "group",
                "sidebar_max_scrolls": 16,
                "chat_max_scrolls": 10,
                "report_custom_prompt": "Summarize key decisions and action items from the chat messages.",
                "llm_provider": "openrouter",
                "openrouter_api_key": "",
                "openai_api_key": "",
                "llm_model": "openai/gpt-4o",
                "output_dir": "output",
            }
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(template, f, ensure_ascii=False, indent=2)
            click.echo(f"[+] Created config: {config_path}")

    click.echo("\n[+] Checking platform prerequisites...")
    import platform as _pf
    if _pf.system() == "Darwin":
        try:
            from platform_mac.grant_permissions import check_accessibility
            check_accessibility()
            click.echo("[+] macOS Accessibility: OK")
        except Exception as e:
            click.echo(f"[!] macOS Accessibility: {e}", err=True)
            click.echo("    Grant Accessibility in System Settings > Privacy & Security.", err=True)
    elif _pf.system() == "Windows":
        try:
            from platform_win.grant_permissions import check_prerequisites
            check_prerequisites()
            click.echo("[+] Windows prerequisites: OK")
        except Exception as e:
            click.echo(f"[!] Windows prerequisites: {e}", err=True)
    else:
        click.echo(f"[!] Unsupported platform: {_pf.system()}", err=True)
        sys.exit(1)

    click.echo(f"\n[+] Setup complete!")
    click.echo("\nNext steps:")
    click.echo(f"  1. Edit {config_path}")
    click.echo("     - Set llm_provider and its API key")
    click.echo("     - OpenAI: export OPENAI_API_KEY or set openai_api_key")
    click.echo("     - OpenRouter: export OPENROUTER_API_KEY or set openrouter_api_key")
    click.echo("     - Set groups_to_monitor")
    click.echo("  2. Run: weclaw run")
