"""Natural Language Strategy Lab commands."""
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

import click
from cli_anything.tradecraft.utils.api_client import APIError, get as api_get, post as api_post
from cli_anything.tradecraft.main import _emit, _dry_run
from cli_anything.tradecraft.core.session import set_key, get as session_get


def _save_to_session(strategy: Dict[str, Any]) -> None:
    """Save strategy to local session cache for review command."""
    strategies = session_get("strategies", [])
    # Remove existing entry with same id
    strategies = [s for s in strategies if s.get("id") != strategy.get("id")]
    strategies.append(strategy)
    set_key("strategies", strategies[-20:])  # Keep last 20


def _find_in_session(strategy_id: str) -> Optional[Dict[str, Any]]:
    """Find a strategy in local session cache."""
    for s in session_get("strategies", []):
        if s.get("id") == strategy_id:
            return s
    return None


@click.group()
def strategy():
    """Natural Language Strategy Lab commands."""


@strategy.command("create")
@click.argument("prompt")
@click.option("--tickers", required=True, help="Comma-separated tickers.")
@click.option("--start-date", default="2020-01-01", help="Start date (default: 2020-01-01).")
@click.option("--end-date", help="End date (default: latest available).")
def strategy_create(prompt: str, tickers: str, start_date: str, end_date: Optional[str]):
    """Generate a trading strategy from natural language description.

    PROMPT is the natural language description (e.g. "mean reversion on AAPL using RSI(30/70)").
    """
    body = {
        "prompt": prompt,
        "tickers": [t.strip().upper() for t in tickers.split(",")],
        "start_date": start_date,
    }
    if end_date:
        body["end_date"] = end_date

    try:
        resp = api_post("/api/generate", body=body)
        # Use backend ID if available, otherwise fall back to local UUID
        strategy_id = resp.get("data", {}).get("id") or str(uuid.uuid4())[:8]
        result = {
            "id": strategy_id,
            "prompt": prompt,
            "tickers": body["tickers"],
            "start_date": start_date,
            "end_date": end_date or "latest",
            "summary": resp.get("data", {}).get("summary", ""),
            "code": resp.get("data", {}).get("code", ""),
            "raw": resp,
            "created_at": datetime.now().isoformat(),
        }
        if not _dry_run():
            _save_to_session(result)
        _emit(result, title="Strategy Generated")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@strategy.command("review")
@click.argument("strategy_id")
def strategy_review(strategy_id: str):
    """Show the summary and generated code for a strategy."""
    s = _find_in_session(strategy_id)
    if not s:
        click.echo(f"Strategy {strategy_id} not found in session cache.", err=True)
        click.echo("Run 'tradecraft strategy create' first, or use 'tradecraft strategy show' for saved strategies.", err=True)
        raise SystemExit(1)
    _emit(s, title=f"Strategy: {strategy_id}")


@strategy.command("backtest")
@click.argument("strategy_id")
@click.option("--tickers", help="Override tickers (comma-separated).")
def strategy_backtest(strategy_id: str, tickers: Optional[str]):
    """Run backtest for a generated strategy."""
    s = _find_in_session(strategy_id)
    if not s:
        click.echo(f"Strategy {strategy_id} not found in session cache.", err=True)
        raise SystemExit(1)

    body = {"code": s["code"], "use_database": True}
    if tickers:
        body["tickers"] = [t.strip().upper() for t in tickers.split(",")]

    try:
        resp = api_post("/api/run", body=body)
        result = {
            "strategy_id": strategy_id,
            "prompt": s["prompt"],
            "tickers": body.get("tickers", s["tickers"]),
            "metrics": {
                "total_return": resp.get("data", {}).get("total_return"),
                "win_rate": resp.get("data", {}).get("win_rate"),
                "sharpe_ratio": resp.get("data", {}).get("sharpe_ratio"),
                "max_drawdown": resp.get("data", {}).get("max_drawdown"),
                "expectancy": resp.get("data", {}).get("expectancy"),
                "n_trades": resp.get("data", {}).get("n_trades"),
                "n_open": resp.get("data", {}).get("n_open"),
            },
            "equity_curve": resp.get("data", {}).get("equity_curve", []),
            "drawdown_curve": resp.get("data", {}).get("drawdown_curve", []),
            "raw": resp,
        }
        _emit(result, title="Backtest Results")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@strategy.command("test-on")
@click.argument("strategy_id")
@click.option("--tickers", required=True, help="Comma-separated tickers to test on.")
def strategy_test_on(strategy_id: str, tickers: str):
    """Run backtest on multiple tickers and return a comparison."""
    s = _find_in_session(strategy_id)
    if not s:
        click.echo(f"Strategy {strategy_id} not found in session cache.", err=True)
        raise SystemExit(1)

    ticker_list = [t.strip().upper() for t in tickers.split(",")]
    results = []
    for t in ticker_list:
        body = {"code": s["code"], "tickers": [t], "use_database": True}
        try:
            resp = api_post("/api/run", body=body)
            d = resp.get("data", {})
            results.append({
                "ticker": t,
                "total_return": d.get("total_return"),
                "win_rate": d.get("win_rate"),
                "sharpe_ratio": d.get("sharpe_ratio"),
                "max_drawdown": d.get("max_drawdown"),
                "n_trades": d.get("n_trades"),
            })
        except APIError as e:
            results.append({"ticker": t, "error": str(e)})

    comparison = {
        "strategy_id": strategy_id,
        "prompt": s["prompt"],
        "results": results,
    }
    _emit(comparison, title="Multi-Asset Comparison")


@strategy.command("save")
@click.argument("strategy_id")
@click.option("--name", required=True, help="Name to save the strategy as.")
@click.option("--notes", help="Optional notes.")
def strategy_save(strategy_id: str, name: str, notes: Optional[str]):
    """Save a strategy to the database for later use."""
    s = _find_in_session(strategy_id)
    if not s:
        click.echo(f"Strategy {strategy_id} not found in session cache.", err=True)
        raise SystemExit(1)

    body = {
        "name": name,
        "code": s["code"],
        "prompt": s["prompt"],
        "tickers": s["tickers"],
        "notes": notes or "",
    }
    try:
        resp = api_post("/api/strategies", body=body)
        _emit({"name": name, "strategy_id": strategy_id, **resp}, title="Strategy Saved")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@strategy.command("list")
@click.option("--kind", help="Filter by kind (screener, quantgen, markov, manual).")
def strategy_list(kind: Optional[str]):
    """List saved strategies."""
    try:
        data = api_get("/api/strategies")
        if kind and isinstance(data, list):
            data = [s for s in data if s.get("kind") == kind]
        _emit(data, title="Saved Strategies")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@strategy.command("show")
@click.argument("name")
def strategy_show(name: str):
    """Show a saved strategy's full details."""
    try:
        data = api_get(f"/api/strategies/{name}")
        _emit(data, title=f"Strategy: {name}")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
