"""Coach / Performance Analytics commands."""
from datetime import datetime, timedelta, timezone
from typing import Optional

import click
from cli_anything.tradecraft.utils.api_client import APIError, get as api_get, post as api_post
from cli_anything.tradecraft.main import _emit


def _date_range(period_days: int):
    """Compute (period_start, period_end) from a period in days."""
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=period_days)
    return start.isoformat(), end.isoformat()


@click.group()
def coach():
    """Performance analytics and coaching commands."""


@coach.command("kpis")
@click.option("--period", type=int, default=90, help="Analysis period in days (default: 90).")
@click.option("--strategy-id", help="Filter by strategy ID.")
def coach_kpis(period: int, strategy_id: Optional[str]):
    """Get key performance indicators from the trade journal."""
    period_start, period_end = _date_range(period)
    params = {"period_start": period_start, "period_end": period_end}
    if strategy_id:
        params["strategy_id"] = strategy_id
    try:
        data = api_get("/api/coach/metrics/overview", params=params)
        _emit(data, title=f"KPIs (last {period}d)")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@coach.command("report")
@click.option("--period", type=int, default=90, help="Analysis period in days (default: 90).")
@click.option("--strategy-id", help="Filter by strategy ID.")
def coach_report(period: int, strategy_id: Optional[str]):
    """Get an LLM-generated critique report with recommendations."""
    period_start, period_end = _date_range(period)
    body = {"period_start": period_start, "period_end": period_end}
    if strategy_id:
        body["strategy_id"] = strategy_id
    try:
        data = api_post("/api/coach/report", body=body)
        _emit(data, title=f"Coach Report (last {period}d)")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@click.group(name="trades")
def coach_trades():
    """Trade journal CRUD commands."""


@coach_trades.command("list")
@click.option("--strategy-id", help="Filter by strategy ID.")
def coach_trades_list(strategy_id: Optional[str]):
    """List trades from the journal."""
    params = {}
    if strategy_id:
        params["strategy_id"] = strategy_id
    try:
        data = api_get("/api/coach/trades", params=params)
        _emit(data, title="Trades")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@coach_trades.command("add")
@click.option("--ticker", required=True, help="Ticker symbol.")
@click.option("--side", required=True, type=click.Choice(["long", "short"]), help="Trade side.")
@click.option("--qty", required=True, type=float, help="Quantity.")
@click.option("--entry-px", required=True, type=float, help="Entry price.")
@click.option("--notes", help="Optional notes.")
def coach_trades_add(ticker: str, side: str, qty: float, entry_px: float, notes: Optional[str]):
    """Add a trade to the journal."""
    body = {
        "ticker": ticker.upper(),
        "side": side,
        "qty": qty,
        "entry_px": entry_px,
        "entry_at": datetime.utcnow().isoformat(),
        "notes": notes or "",
    }
    try:
        data = api_post("/api/coach/trades", body=body)
        _emit(data, title="Trade Added")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@coach_trades.command("close")
@click.argument("trade_id")
@click.option("--exit-px", type=float, help="Exit price (default: today's close).")
def coach_trades_close(trade_id: str, exit_px: Optional[float]):
    """Close an open trade."""
    body = {}
    if exit_px:
        body["exit_px"] = exit_px
    try:
        data = api_post(f"/api/coach/trades/{trade_id}/close", body=body)
        _emit(data, title="Trade Closed")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


# Register trades sub-group under coach
coach.add_command(coach_trades)
