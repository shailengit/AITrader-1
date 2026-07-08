"""Sector rotation commands."""
import click
from cli_anything.tradecraft.utils.api_client import APIError, get as api_get
from cli_anything.tradecraft.main import _emit


@click.group()
def sectors():
    """Sector Rotation Scanner commands."""


@sectors.command("list")
def sectors_list():
    """List all sector ETF performance data."""
    try:
        data = api_get("/api/sectors")
        _emit(data, title="Sector Performance")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@sectors.command("stocks")
@click.argument("sector")
@click.option("--limit", type=int, default=50, help="Limit number of stocks.")
def sector_stocks(sector: str, limit: int):
    """Get top stocks within a sector."""
    try:
        data = api_get(f"/api/stocks/{sector}")
        if isinstance(data, list) and limit:
            data = data[:limit]
        _emit(data, title=f"Stocks in {sector.upper()}")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@sectors.command("ohlcv")
@click.argument("ticker")
@click.option("--days", type=int, default=150, help="Number of days.")
def sector_ohlcv(ticker: str, days: int):
    """Get OHLCV data for a ticker."""
    try:
        data = api_get(f"/api/ohlcv/{ticker}")
        if isinstance(data, list) and days:
            data = data[-days:]
        _emit(data, title=f"OHLCV for {ticker.upper()}")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
