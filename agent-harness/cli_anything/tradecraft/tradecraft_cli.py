"""TradeCraft CLI entry point.

Usage:
    cli-anything-tradecraft --help
    cli-anything-tradecraft health
    cli-anything-tradecraft sectors list
    cli-anything-tradecraft screener scan --mode dormant_giant
    cli-anything-tradecraft quantgen generate --prompt "..."
    cli-anything-tradecraft repl
"""

import json
import os
import shlex
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import click

from cli_anything.tradecraft.core.config import (
    load_config,
    save_config,
    get_backend_url,
    set_backend_url,
    get_output_format,
    set_output_format,
)
from cli_anything.tradecraft.core.session import Session
from cli_anything.tradecraft.core.project import Project
from cli_anything.tradecraft.core.export import emit
from cli_anything.tradecraft.utils.api_client import (
    APIError,
    get as api_get,
    post as api_post,
    delete as api_delete,
)


def _json_flag() -> bool:
    return click.get_current_context().obj.get("json", False) if click.get_current_context().obj else False


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
    """TradeCraft CLI - Sector Rotation, AI Screener, and QuantGen Strategy Builder."""
    ctx.ensure_object(dict)
    ctx.obj["json"] = json_output
    ctx.obj["dry_run"] = dry_run
    if backend:
        os.environ["TRADECRAFT_BACKEND_URL"] = backend
    # Ensure config is loaded
    ctx.obj["config"] = load_config()


# =============================================================================
# Health
# =============================================================================

@cli.command()
def health():
    """Check TradeCraft API and database health."""
    try:
        data = api_get("/api/health")
        _emit(data, title="API Health")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
def db_status():
    """Check database connection status."""
    try:
        data = api_get("/api/db-status")
        _emit(data, title="Database Status")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


# =============================================================================
# Sectors
# =============================================================================

@cli.group()
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
        sys.exit(1)


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
        sys.exit(1)


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
        sys.exit(1)


# =============================================================================
# Screener
# =============================================================================

@cli.group()
def screener():
    """AI Stock Screener commands."""


@screener.command("modes")
def screener_modes():
    """List available screening modes."""
    try:
        data = api_get("/api/screener/modes")
        _emit(data, title="Screener Modes")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@screener.command("scan")
@click.option("--mode", default="dormant_giant", type=click.Choice(["dormant_giant", "quant_strategy"]), help="Scan mode.")
@click.option("--use-ai/--no-ai", default=True, help="Use AI multi-agent analysis.")
@click.option("--prompt", help="Custom prompt for AI analysis.")
@click.option("--cutoff-date", help="Cutoff date for quant_strategy backtesting.")
@click.option("--max-results", type=int, default=50, help="Max results.")
@click.option("--filters", type=click.Path(exists=True), help="JSON file with filter criteria.")
@click.option("--project", help="Associate scan with a project.")
@click.option("--wait", is_flag=True, help="Poll until scan completes.")
@click.option("--interval", type=int, default=3, help="Polling interval in seconds.")
def screener_scan(
    mode: str,
    use_ai: bool,
    prompt: Optional[str],
    cutoff_date: Optional[str],
    max_results: int,
    filters: Optional[str],
    project: Optional[str],
    wait: bool,
    interval: int,
):
    """Run a stock screening scan."""
    body: Dict[str, Any] = {
        "mode": mode,
        "use_ai": use_ai,
        "max_results": max_results,
    }
    if prompt:
        body["prompt"] = prompt
    if cutoff_date:
        body["cutoff_date"] = cutoff_date
    if filters:
        body["filters"] = json.loads(Path(filters).read_text(encoding="utf-8"))

    try:
        resp = api_post("/api/screener/scan", body=body)
        scan_id = resp.get("scan_id")
        if scan_id:
            session = Session(dry_run=_dry_run())
            session.add_scan(scan_id, mode, use_ai)
            if project:
                p = Project(project)
                p.add_scan(scan_id)
        _emit(resp, title="Scan Started")

        if wait and scan_id:
            click.echo(f"Waiting for scan {scan_id}...")
            _poll_scan(scan_id, interval)
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def _poll_scan(scan_id: str, interval: int) -> None:
    while True:
        time.sleep(interval)
        try:
            status = api_get(f"/api/screener/status/{scan_id}")
            s = status.get("status", "unknown")
            progress = status.get("progress", 0)
            click.echo(f"  [{s}] {progress}%")
            if s in ("completed", "failed"):
                _emit(status, title="Scan Complete")
                session = Session(dry_run=_dry_run())
                session.update_scan_status(scan_id, s)
                break
        except APIError:
            click.echo("  Polling error, retrying...")


@screener.command("status")
@click.argument("scan_id")
def screener_status(scan_id: str):
    """Get scan status."""
    try:
        data = api_get(f"/api/screener/status/{scan_id}")
        _emit(data, title=f"Scan Status: {scan_id}")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@screener.command("results")
@click.argument("scan_id")
def screener_results(scan_id: str):
    """Get scan results."""
    try:
        data = api_get(f"/api/screener/results/{scan_id}")
        _emit(data, title=f"Scan Results: {scan_id}")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@screener.command("report")
@click.argument("scan_id")
@click.option("--output", "-o", help="Output file path for PDF.")
def screener_report(scan_id: str, output: Optional[str]):
    """Download a PDF report for a completed scan."""
    try:
        base = get_backend_url()
        url = f"{base}/api/screener/report/{scan_id}"
        import urllib.request
        req = urllib.request.Request(url, headers={"Accept": "application/pdf"})
        resp = urllib.request.urlopen(req)
        pdf_bytes = resp.read()
        if output:
            Path(output).write_bytes(pdf_bytes)
            click.echo(f"PDF saved to {output}")
        else:
            safe_name = f"tradecraft-screener-{scan_id[:8]}.pdf"
            Path(safe_name).write_bytes(pdf_bytes)
            click.echo(f"PDF saved to {safe_name}")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@screener.command("delete")
@click.argument("scan_id")
def screener_delete(scan_id: str):
    """Delete a scan."""
    try:
        data = api_delete(f"/api/screener/scan/{scan_id}")
        session = Session(dry_run=_dry_run())
        session.remove_scan(scan_id)
        _emit(data, title="Scan Deleted")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@screener.command("list")
def screener_list():
    """List locally tracked scans from session history."""
    session = Session(dry_run=_dry_run())
    scans = session.get_scans()
    if not scans:
        click.echo("No tracked scans. Run 'screener scan' to start one.")
        return
    _emit(scans, title="Tracked Scans")


@screener.command("ai-report")
@click.argument("scan_id")
def screener_ai_report(scan_id: str):
    """Get the AI-generated analysis report for a completed scan."""
    try:
        data = api_get(f"/api/screener/ai-report/{scan_id}")
        _emit(data, title=f"AI Report: {scan_id}")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@screener.command("health")
def screener_health():
    """Check screener service health and active scan count."""
    try:
        data = api_get("/api/screener/health")
        _emit(data, title="Screener Health")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


# =============================================================================
# QuantGen
# =============================================================================

@cli.group()
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
        sys.exit(1)


@quantgen.command("generate")
@click.option("--prompt", required=True, help="Strategy generation prompt.")
@click.option("--tickers", required=True, help="Comma-separated tickers.")
@click.option("--start-date", default="2020-01-01", help="Start date.")
@click.option("--end-date", default="2024-01-01", help="End date.")
@click.option("--output", "-o", help="Save generated code to file.")
def quantgen_generate(
    prompt: str,
    tickers: str,
    start_date: str,
    end_date: str,
    output: Optional[str],
):
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
        sys.exit(1)


@quantgen.command("run")
@click.option("--code", help="Strategy code string.")
@click.option("--file", "-f", type=click.Path(exists=True), help="Strategy code file.")
@click.option("--use-database/--no-database", default=True, help="Use database for data.")
def quantgen_run(code: Optional[str], file: Optional[str], use_database: bool):
    """Execute a trading strategy."""
    if file:
        code = Path(file).read_text(encoding="utf-8")
    if not code:
        click.echo("Error: --code or --file required.", err=True)
        sys.exit(1)
    body = {"code": code, "use_database": use_database}
    try:
        resp = api_post("/api/run", body=body)
        _emit(resp, title="Strategy Run")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@quantgen.command("optimize")
@click.option("--code", help="Strategy code string.")
@click.option("--file", "-f", type=click.Path(exists=True), help="Strategy code file.")
@click.option("--params-file", type=click.Path(exists=True), help="JSON file with strategy_params.")
@click.option("--config-file", type=click.Path(exists=True), help="JSON file with optimization config.")
@click.option("--mode", default="rolling", type=click.Choice(["rolling", "true_wfo"]), help="Optimization mode.")
def quantgen_optimize(
    code: Optional[str],
    file: Optional[str],
    params_file: Optional[str],
    config_file: Optional[str],
    mode: str,
):
    """Run parameter optimization on a strategy."""
    if file:
        code = Path(file).read_text(encoding="utf-8")
    if not code:
        click.echo("Error: --code or --file required.", err=True)
        sys.exit(1)

    strategy_params: Dict[str, Any] = {}
    if params_file:
        strategy_params = json.loads(Path(params_file).read_text(encoding="utf-8"))

    config: Dict[str, Any] = {"mode": mode}
    if config_file:
        config = json.loads(Path(config_file).read_text(encoding="utf-8"))
        config.setdefault("mode", mode)

    body = {"code": code, "strategy_params": strategy_params, "config": config}
    try:
        resp = api_post("/api/optimize", body=body)
        _emit(resp, title="Optimization Results")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@quantgen.command("chat")
@click.option("--code", help="Strategy code string.")
@click.option("--file", "-f", type=click.Path(exists=True), help="Strategy code file.")
@click.option("--message", required=True, help="Chat message.")
def quantgen_chat(code: Optional[str], file: Optional[str], message: str):
    """Chat about strategy code with AI."""
    if file:
        code = Path(file).read_text(encoding="utf-8")
    if not code:
        click.echo("Error: --code or --file required.", err=True)
        sys.exit(1)
    body = {"code": code, "messages": [{"role": "user", "content": message}]}
    try:
        resp = api_post("/api/chat", body=body)
        _emit(resp, title="Chat Response")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@quantgen.command("indicators")
def quantgen_indicators():
    """List available technical indicators."""
    try:
        data = api_get("/api/indicators")
        _emit(data, title="Technical Indicators")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@quantgen.command("true-wfo")
@click.option("--code", help="Strategy code string.")
@click.option("--file", "-f", type=click.Path(exists=True), help="Strategy code file.")
@click.option("--params-file", type=click.Path(exists=True), help="JSON file with strategy_params.")
@click.option("--config-file", type=click.Path(exists=True), help="JSON file with optimization config.")
def quantgen_true_wfo(
    code: Optional[str],
    file: Optional[str],
    params_file: Optional[str],
    config_file: Optional[str],
):
    """Run True Walk-Forward Optimization (deprecated endpoint)."""
    if file:
        code = Path(file).read_text(encoding="utf-8")
    if not code:
        click.echo("Error: --code or --file required.", err=True)
        sys.exit(1)

    strategy_params: Dict[str, Any] = {}
    if params_file:
        strategy_params = json.loads(Path(params_file).read_text(encoding="utf-8"))

    config: Dict[str, Any] = {}
    if config_file:
        config = json.loads(Path(config_file).read_text(encoding="utf-8"))

    body = {"code": code, "strategy_params": strategy_params, "config": config}
    try:
        resp = api_post("/api/true-wfo", body=body)
        _emit(resp, title="True WFO Results")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


# =============================================================================
# Strategies
# =============================================================================

@cli.group()
def strategies():
    """Strategy file management commands."""


@strategies.command("list")
def strategies_list():
    """List saved strategies on the backend."""
    try:
        data = api_get("/api/strategies")
        _emit(data, title="Saved Strategies")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@strategies.command("get")
@click.argument("name")
def strategies_get(name: str):
    """Get a saved strategy by name."""
    try:
        data = api_get(f"/api/strategies/{name}")
        _emit(data, title=f"Strategy: {name}")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@strategies.command("save")
@click.argument("name")
@click.option("--file", "-f", type=click.Path(exists=True), required=True, help="Strategy code file.")
@click.option("--project", help="Associate with a project.")
def strategies_save(name: str, file: str, project: Optional[str]):
    """Save a strategy to the backend."""
    code = Path(file).read_text(encoding="utf-8")
    body = {"name": name, "code": code}
    try:
        resp = api_post("/api/strategies", body=body)
        if project:
            p = Project(project)
            p.add_strategy(name)
        _emit(resp, title="Strategy Saved")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@strategies.command("delete")
@click.argument("name")
def strategies_delete(name: str):
    """Delete a saved strategy."""
    try:
        data = api_delete(f"/api/strategies/{name}")
        _emit(data, title="Strategy Deleted")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


# =============================================================================
# Projects
# =============================================================================

@cli.group()
def projects():
    """Project management commands."""


@projects.command("list")
def projects_list():
    """List all projects."""
    names = Project.list_all()
    _emit({"projects": names}, title="Projects")


@projects.command("create")
@click.argument("name")
def projects_create(name: str):
    """Create a new project."""
    p = Project(name)
    p.save()
    _emit({"name": name, "message": "Project created"}, title="Project Created")


@projects.command("show")
@click.argument("name")
def projects_show(name: str):
    """Show project details."""
    p = Project(name)
    _emit({
        "name": name,
        "scans": p.list_scans(),
        "strategies": p.list_strategies(),
        "notes": p._data.get("notes", ""),
    }, title=f"Project: {name}")


@projects.command("delete")
@click.argument("name")
def projects_delete(name: str):
    """Delete a project."""
    if Project.delete(name):
        _emit({"name": name, "message": "Project deleted"}, title="Project Deleted")
    else:
        click.echo(f"Project '{name}' not found.", err=True)
        sys.exit(1)


@projects.command("notes")
@click.argument("name")
@click.option("--set", "notes_text", help="Set project notes text.")
@click.option("--file", type=click.Path(exists=True), help="Read notes from file.")
def projects_notes(name: str, notes_text: Optional[str], file: Optional[str]):
    """Show or set project notes."""
    p = Project(name)
    if file:
        notes_text = Path(file).read_text(encoding="utf-8")
    if notes_text is not None:
        p.set_notes(notes_text)
        _emit({"name": name, "message": "Notes updated"}, title="Project Notes Updated")
    else:
        _emit({"name": name, "notes": p.get_notes()}, title=f"Project Notes: {name}")


@projects.command("add-scan")
@click.argument("name")
@click.argument("scan_id")
def projects_add_scan(name: str, scan_id: str):
    """Associate an existing scan with a project."""
    p = Project(name)
    p.add_scan(scan_id)
    _emit({"name": name, "scan_id": scan_id, "message": "Scan added"}, title="Scan Added")


@projects.command("add-strategy")
@click.argument("name")
@click.argument("strategy")
def projects_add_strategy(name: str, strategy: str):
    """Associate an existing strategy with a project."""
    p = Project(name)
    p.add_strategy(strategy)
    _emit({"name": name, "strategy": strategy, "message": "Strategy added"}, title="Strategy Added")


# =============================================================================
# Config
# =============================================================================

@cli.group()
def config():
    """Configuration commands."""


@config.command("show")
def config_show():
    """Show current configuration."""
    cfg = load_config()
    _emit(cfg, title="Configuration")


@config.command("set-url")
@click.argument("url")
@click.option("--dry-run", is_flag=True, hidden=True)
def config_set_url(url: str, dry_run: bool):
    """Set the backend URL."""
    if not dry_run:
        set_backend_url(url)
    _emit({"backend_url": url}, title="Backend URL Set")


@config.command("set-format")
@click.argument("fmt", type=click.Choice(["table", "json", "csv"]))
def config_set_format(fmt: str):
    """Set default output format."""
    set_output_format(fmt)
    _emit({"output_format": fmt}, title="Output Format Set")


# =============================================================================
# REPL
# =============================================================================

@cli.command()
@click.pass_context
def repl(ctx):
    """Start an interactive REPL session."""
    click.echo("TradeCraft CLI REPL. Type 'help' for commands, 'exit' to quit.")
    while True:
        try:
            user_input = input("tradecraft> ")
        except (EOFError, KeyboardInterrupt):
            click.echo("\nExiting REPL.")
            break
        user_input = user_input.strip()
        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            break
        if user_input.lower() == "help":
            click.echo(ctx.parent.get_help() if ctx.parent else cli.get_help(ctx))
            continue
        try:
            cli.main(shlex.split(user_input), prog_name="cli-anything-tradecraft", standalone_mode=False)
        except SystemExit:
            pass
        except Exception as e:
            click.echo(f"Error: {e}", err=True)


# =============================================================================
# Entry point
# =============================================================================

def main():
    cli()


if __name__ == "__main__":
    main()
