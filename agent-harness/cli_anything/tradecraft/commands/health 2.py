"""Health check commands."""
import click
from cli_anything.tradecraft.utils.api_client import APIError, get as api_get
from cli_anything.tradecraft.main import _emit


@click.command()
def health():
    """Check TradeCraft API and database health."""
    try:
        data = api_get("/api/health")
        _emit(data, title="API Health")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@click.command(name="db-status")
def db_status():
    """Check database connection status."""
    try:
        data = api_get("/api/db-status")
        _emit(data, title="Database Status")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
