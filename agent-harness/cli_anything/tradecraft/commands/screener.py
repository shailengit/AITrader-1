"""AI Stock Screener commands."""
import json
import time
from pathlib import Path
from typing import Optional

import click
from cli_anything.tradecraft.utils.api_client import APIError, get as api_get, post as api_post, delete as api_delete
from cli_anything.tradecraft.main import _emit, _dry_run
from cli_anything.tradecraft.core.session import set_key


@click.group()
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
        raise SystemExit(1)


@screener.command("scan")
@click.option("--mode", default="dormant_giant", type=click.Choice(["dormant_giant", "quant_strategy"]))
@click.option("--use-ai/--no-ai", default=True)
@click.option("--prompt", help="Custom prompt for AI analysis.")
@click.option("--cutoff-date", help="Cutoff date for quant_strategy backtesting.")
@click.option("--max-results", type=int, default=50)
@click.option("--filters", type=click.Path(exists=True), help="JSON file with filter criteria.")
@click.option("--project", help="Associate scan with a project.")
@click.option("--wait", is_flag=True, help="Poll until scan completes.")
@click.option("--interval", type=int, default=3, help="Polling interval in seconds.")
def screener_scan(mode, use_ai, prompt, cutoff_date, max_results, filters, project, wait, interval):
    """Start a stock screening scan."""
    body = {"mode": mode, "use_ai": use_ai, "max_results": max_results}
    if prompt:
        body["prompt"] = prompt
    if cutoff_date:
        body["cutoff_date"] = cutoff_date
    if filters:
        body["filters"] = json.loads(Path(filters).read_text(encoding="utf-8"))
    if project:
        body["project"] = project
    try:
        resp = api_post("/api/screener/scan", body=body)
        scan_id = resp.get("scan_id")
        if not _dry_run() and scan_id:
            history = __import__("cli_anything.tradecraft.core.session", fromlist=["get"]).get("scans", [])
            history.append({"scan_id": scan_id, "mode": mode, "prompt": prompt})
            set_key("scans", history[-20:])
        if wait and scan_id:
            click.echo(f"Scan {scan_id} started, polling every {interval}s...")
            for _ in range(120):
                status_resp = api_get(f"/api/screener/status/{scan_id}")
                if status_resp.get("status") in ("completed", "failed"):
                    _emit(status_resp, title="Scan Complete")
                    return
                time.sleep(interval)
            click.echo("Timed out waiting for scan.", err=True)
        else:
            _emit(resp, title="Scan Started")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@screener.command("list")
def screener_list():
    """List recent scans."""
    try:
        data = api_get("/api/screener/scans")
        _emit(data, title="Recent Scans")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@screener.command("status")
@click.argument("scan_id")
def screener_status(scan_id: str):
    """Check scan status."""
    try:
        data = api_get(f"/api/screener/status/{scan_id}")
        _emit(data, title="Scan Status")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@screener.command("results")
@click.argument("scan_id")
def screener_results(scan_id: str):
    """Get scan results."""
    try:
        data = api_get(f"/api/screener/results/{scan_id}")
        _emit(data, title="Scan Results")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@screener.command("ai-report")
@click.argument("scan_id")
def screener_ai_report(scan_id: str):
    """Get AI analysis report for a scan."""
    try:
        data = api_get(f"/api/screener/ai-report/{scan_id}")
        _emit(data, title="AI Report")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@screener.command("delete")
@click.argument("scan_id")
def screener_delete(scan_id: str):
    """Delete a scan."""
    try:
        data = api_delete(f"/api/screener/scan/{scan_id}")
        _emit(data, title="Scan Deleted")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@screener.command("health")
def screener_health():
    """Check screener service health."""
    try:
        data = api_get("/api/screener/health")
        _emit(data, title="Screener Health")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
