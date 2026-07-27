"""QuantGen Strategy Builder commands."""
import json
from pathlib import Path
from typing import Optional

import click
from cli_anything.tradecraft.utils.api_client import APIError, get as api_get, post as api_post
from cli_anything.tradecraft.main import _emit


@click.group()
def quantgen():
    """QuantGen Strategy Builder commands."""


@quantgen.command("health")
def quantgen_health():
    """Check QuantGen module health."""
    try:
        data = api_get("/api/health")
        _emit(data, title="QuantGen Health")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@quantgen.command("generate")
@click.option("--prompt", required=True, help="Strategy generation prompt.")
@click.option("--tickers", required=True, help="Comma-separated tickers.")
@click.option("--start-date", default="2020-01-01", help="Start date.")
@click.option("--end-date", default="2024-01-01", help="End date.")
@click.option("--output", "-o", help="Save generated code to file.")
def quantgen_generate(prompt: str, tickers: str, start_date: str, end_date: str, output: Optional[str]):
    """Generate a trading strategy using AI."""
    body = {
        "prompt": prompt,
        "tickers": [t.strip().upper() for t in tickers.split(",")],
        "start_date": start_date,
        "end_date": end_date,
    }
    try:
        resp = api_post("/api/generate", body=body)
        if output and resp.get("success"):
            code = resp.get("data", {}).get("code", "")
            Path(output).write_text(code, encoding="utf-8")
            click.echo(f"Code saved to {output}")
        _emit(resp, title="Strategy Generated")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@quantgen.command("run")
@click.option("--code", help="Strategy code string.")
@click.option("--file", "-f", type=click.Path(exists=True), help="Strategy code file.")
@click.option("--use-database/--no-database", default=True)
def quantgen_run(code: Optional[str], file: Optional[str], use_database: bool):
    """Execute a trading strategy."""
    if file:
        code = Path(file).read_text(encoding="utf-8")
    if not code:
        click.echo("Error: --code or --file required.", err=True)
        raise SystemExit(1)
    body = {"code": code, "use_database": use_database}
    try:
        resp = api_post("/api/run", body=body)
        _emit(resp, title="Strategy Run")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@quantgen.command("optimize")
@click.option("--code", help="Strategy code string.")
@click.option("--file", "-f", type=click.Path(exists=True), help="Strategy code file.")
@click.option("--params-file", type=click.Path(exists=True), help="JSON file with strategy_params.")
@click.option("--config-file", type=click.Path(exists=True), help="JSON file with optimization config.")
@click.option("--mode", default="rolling", type=click.Choice(["rolling", "true_wfo"]))
def quantgen_optimize(code: Optional[str], file: Optional[str], params_file: Optional[str], config_file: Optional[str], mode: str):
    """Run parameter optimization on a strategy."""
    if file:
        code = Path(file).read_text(encoding="utf-8")
    if not code:
        click.echo("Error: --code or --file required.", err=True)
        raise SystemExit(1)
    strategy_params = {}
    if params_file:
        strategy_params = json.loads(Path(params_file).read_text(encoding="utf-8"))
    config = {"mode": mode}
    if config_file:
        config = json.loads(Path(config_file).read_text(encoding="utf-8"))
        config.setdefault("mode", mode)
    body = {"code": code, "strategy_params": strategy_params, "config": config}
    try:
        resp = api_post("/api/optimize", body=body)
        _emit(resp, title="Optimization Results")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@quantgen.command("chat")
@click.option("--message", required=True, help="Chat message about strategy code.")
@click.option("--code", help="Strategy code context.")
@click.option("--file", "-f", type=click.Path(exists=True), help="Strategy code file.")
def quantgen_chat(message: str, code: Optional[str], file: Optional[str]):
    """Chat about strategy code."""
    if file:
        code = Path(file).read_text(encoding="utf-8")
    body = {"message": message}
    if code:
        body["code"] = code
    try:
        resp = api_post("/api/chat", body=body)
        _emit(resp, title="Chat Response")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@quantgen.command("indicators")
def quantgen_indicators():
    """List available technical indicators."""
    try:
        data = api_get("/api/indicators")
        _emit(data, title="Available Indicators")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
