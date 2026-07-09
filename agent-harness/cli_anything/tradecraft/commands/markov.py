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
        data = api_get("/api/markov/status")
        _emit(data, title="Markov Status")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@markov.command("train")
def markov_train():
    """Trigger model retraining."""
    try:
        data = api_post("/api/markov/retrain", body={})
        _emit(data, title="Training Started")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@markov.command("retrain-status")
def markov_retrain_status():
    """Check retraining progress."""
    try:
        data = api_get("/api/markov/retrain-status")
        _emit(data, title="Retrain Status")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
