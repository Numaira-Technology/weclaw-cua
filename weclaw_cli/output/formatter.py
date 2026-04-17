"""CLI output formatting utilities."""

import json

import click


def output(value, fmt: str = "json") -> None:
    """Render command output as JSON or text."""
    if fmt == "json":
        click.echo(json.dumps(value, ensure_ascii=False, indent=2))
        return

    if isinstance(value, (dict, list)):
        click.echo(json.dumps(value, ensure_ascii=False, indent=2))
        return

    click.echo(value)
