"""Markov Chain Trader commands."""
from typing import Optional

import click
from cli_anything.tradecraft.utils.api_client import APIError, get as api_get, post as api_post
from cli_anything.tradecraft.main import _emit


@click.group()
def markov():
    """Markov Chain Trader learning agent commands."""


@markov.command("status")
def markov_status():
    """Show model training status and health."""
    try:
        data = api_get("/markov/status")
        _emit(data, title="Markov Status")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@markov.command("train")
@click.option("--model", type=click.Choice(["xgboost", "lstm"]), help="Model to train (default: all).")
def markov_train(model: Optional[str]):
    """Trigger model retraining."""
    body = {}
    if model:
        body["model"] = model
    try:
        data = api_post("/markov/train", body=body)
        _emit(data, title="Training Started")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@markov.command("signal")
@click.argument("ticker")
@click.option("--date", help="Date (YYYY-MM-DD, default: latest).")
def markov_signal(ticker: str, date: Optional[str]):
    """Get conviction signal for a ticker."""
    params = {"ticker": ticker.upper()}
    if date:
        params["date"] = date
    try:
        data = api_get("/markov/signal", params=params)
        _emit(data, title=f"Signal for {ticker.upper()}")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
