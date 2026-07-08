"""TradeCraft CLI entry point.

Usage:
    tradecraft --help
    tradecraft --json health
    tradecraft strategy create "mean reversion on AAPL" --tickers AAPL
    tradecraft coach kpis --period 90
    tradecraft markov status
"""
import json
import os
import sys
from typing import Any, Optional

import click

from cli_anything.tradecraft.core.config import load_config
from cli_anything.tradecraft.core.export import emit


def _json_flag() -> bool:
    ctx = click.get_current_context()
    return ctx.obj.get("json", False) if ctx and ctx.obj else False

def _dry_run() -> bool:
    ctx = click.get_current_context()
    return ctx.obj.get("dry_run", False) if ctx and ctx.obj else False

def _emit(data: Any, title: str = "") -> None:
    if _json_flag():
        click.echo(json.dumps(data, indent=2, default=str))
    else:
        emit(data, title=title)


@click.group(invoke_without_command=False)
@click.option("--json", "json_output", is_flag=True, help="Output raw JSON for agent consumption.")
@click.option("--dry-run", is_flag=True, help="Do not persist local state changes.")
@click.option("--backend", help="Override backend URL.")
@click.pass_context
def cli(ctx, json_output: bool, dry_run: bool, backend: Optional[str]):
    """TradeCraft CLI — strategy creation, backtesting, coach analytics, Markov learning."""
    ctx.ensure_object(dict)
    ctx.obj["json"] = json_output
    ctx.obj["dry_run"] = dry_run
    if backend:
        os.environ["TRADECRAFT_BACKEND_URL"] = backend
    ctx.obj["config"] = load_config()


# Import and register command groups
from cli_anything.tradecraft.commands.health import health, db_status
from cli_anything.tradecraft.commands.sectors import sectors
from cli_anything.tradecraft.commands.screener import screener
from cli_anything.tradecraft.commands.quantgen import quantgen
from cli_anything.tradecraft.commands.strategies import strategies
from cli_anything.tradecraft.commands.strategy import strategy
from cli_anything.tradecraft.commands.coach import coach
from cli_anything.tradecraft.commands.markov import markov
from cli_anything.tradecraft.commands.projects import projects
from cli_anything.tradecraft.commands.config_cmd import config_cmd
from cli_anything.tradecraft.commands.repl import repl

cli.add_command(health)
cli.add_command(db_status)
cli.add_command(sectors)
cli.add_command(screener)
cli.add_command(quantgen)
cli.add_command(strategies)
cli.add_command(strategy)
cli.add_command(coach)
cli.add_command(markov)
cli.add_command(projects)
cli.add_command(config_cmd)
cli.add_command(repl)


def main():
    cli()

if __name__ == "__main__":
    main()
