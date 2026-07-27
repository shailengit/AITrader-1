"""Strategy persistence commands."""
import click
from cli_anything.tradecraft.utils.api_client import APIError, get as api_get, delete as api_delete
from cli_anything.tradecraft.main import _emit


@click.group()
def strategies():
    """Saved strategy management commands."""


@strategies.command("list")
def strategies_list():
    """List saved strategies."""
    try:
        data = api_get("/api/strategies")
        _emit(data, title="Saved Strategies")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@strategies.command("show")
@click.argument("name")
def strategies_show(name: str):
    """Show a saved strategy's details."""
    try:
        data = api_get(f"/api/strategies/{name}")
        _emit(data, title=f"Strategy: {name}")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@strategies.command("delete")
@click.argument("name")
def strategies_delete(name: str):
    """Delete a saved strategy."""
    try:
        data = api_delete(f"/api/strategies/{name}")
        _emit(data, title="Strategy Deleted")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
