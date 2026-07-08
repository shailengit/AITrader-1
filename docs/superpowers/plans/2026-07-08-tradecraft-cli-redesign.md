# TradeCraft CLI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the TradeCraft CLI from scratch as a `tradecraft` command that serves as the primary interface for Claude Code to create, backtest, analyze, and learn from trading strategies using natural language.

**Architecture:** A Click-based Python CLI that wraps the FastAPI backend. Commands are organized into groups (strategy, coach, markov, sectors, screener, quantgen, etc.). All commands support `--json` for machine-readable output. A lessons-learned system captures code generation errors and prevents repeats. Claude Code integration via `.claude/settings.json` tool registration and a skill.

**Tech Stack:** Python 3.8+, Click 8.0+, urllib (stdlib, no requests dependency), JSON file storage for config/session/lessons.

## Global Constraints

- All commands must support `--json` flag for machine-readable output
- Config directory: `~/.config/tradecraft/` (not `~/.config/cli-anything-tradecraft/`)
- No external HTTP dependencies beyond stdlib `urllib`
- Every command that makes API calls must handle `APIError` gracefully
- Tests use pytest with no external dependencies (mock API calls with monkeypatch)
- The old `cli-anything-tradecraft` entry point is replaced by `tradecraft`

---

## File Structure

```
agent-harness/
├── setup.py                              # Modified: new entry point "tradecraft"
├── cli_anything/tradecraft/
│   ├── __init__.py
│   ├── main.py                           # New: CLI entry point, Click group, --json/--dry-run/--backend
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py                     # Modified: ~/.config/tradecraft/ dir
│   │   ├── session.py                    # Modified: ~/.config/tradecraft/ dir
│   │   ├── export.py                     # Kept as-is
│   │   ├── project.py                    # Kept as-is
│   │   └── lessons.py                   # New: lessons learned store (CRUD + match)
│   ├── commands/
│   │   ├── __init__.py
│   │   ├── health.py                     # New: health, db-status
│   │   ├── sectors.py                    # New: sectors list, stocks, ohlcv
│   │   ├── screener.py                   # New: screener scan, results, modes, etc.
│   │   ├── quantgen.py                   # New: quantgen generate, run, optimize, chat, indicators
│   │   ├── strategies.py                 # New: strategies list, show, delete
│   │   ├── strategy.py                   # New: strategy create, review, backtest, test-on, save, list, show
│   │   ├── coach.py                      # New: coach kpis, report, trades
│   │   ├── markov.py                     # New: markov status, train, signal
│   │   ├── projects.py                   # New: projects create, show, notes, add-scan, add-strategy, delete
│   │   ├── config_cmd.py                 # New: config get, set, show
│   │   └── repl.py                       # New: interactive shell
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── api_client.py                 # Modified: updated config path
│   │   └── formatters.py                 # Kept as-is
│   └── tests/
│       ├── __init__.py
│       ├── test_core.py                  # Modified: updated config path tests
│       ├── test_strategy.py              # New: strategy command tests
│       ├── test_lessons.py               # New: lessons learned tests
│       └── test_coach.py                 # New: coach command tests
.claude/
├── settings.json                         # New: tool registration
└── skills/tradecraft/SKILL.md            # New: conversation orchestrator
```

---

### Task 1: CLI Foundation — setup.py, main.py, config, API client

**Files:**
- Modify: `agent-harness/setup.py`
- Create: `agent-harness/cli_anything/tradecraft/main.py`
- Modify: `agent-harness/cli_anything/tradecraft/core/config.py`
- Modify: `agent-harness/cli_anything/tradecraft/core/session.py`
- Modify: `agent-harness/cli_anything/tradecraft/utils/api_client.py`
- Keep: `agent-harness/cli_anything/tradecraft/core/export.py`
- Keep: `agent-harness/cli_anything/tradecraft/core/project.py`
- Keep: `agent-harness/cli_anything/tradecraft/utils/formatters.py`

**Interfaces:**
- Consumes: existing `core/export.py`, `core/project.py`, `utils/formatters.py`
- Produces: `main.py` with `@click.group()` entry point, `config.py` with `~/.config/tradecraft/` dir, `api_client.py` with updated config path

- [ ] **Step 1: Update setup.py**

```python
"""Setup script for tradecraft CLI."""
from setuptools import setup, find_namespace_packages

setup(
    name="tradecraft-cli",
    version="0.2.0",
    description="TradeCraft CLI — strategy creation, backtesting, coach analytics, Markov learning",
    packages=find_namespace_packages(include=["cli_anything.*"]),
    namespace_packages=["cli_anything"],
    include_package_data=True,
    python_requires=">=3.8",
    install_requires=[
        "click>=8.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pytest-cov>=4.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "tradecraft=cli_anything.tradecraft.main:cli",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
    ],
)
```

- [ ] **Step 2: Update config.py to use ~/.config/tradecraft/**

```python
"""Configuration management for tradecraft CLI."""
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional

CONFIG_DIR = Path.home() / ".config" / "tradecraft"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "backend_url": "http://localhost:8000",
    "output_format": "table",
    "timeout": 120,
    "auto_save": True,
}

def ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

def load_config() -> Dict[str, Any]:
    ensure_config_dir()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            merged = dict(DEFAULT_CONFIG)
            merged.update(data)
            return merged
        except (json.JSONDecodeError, OSError):
            return dict(DEFAULT_CONFIG)
    return dict(DEFAULT_CONFIG)

def save_config(config: Dict[str, Any]) -> None:
    ensure_config_dir()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

def get_backend_url() -> str:
    return load_config().get("backend_url", DEFAULT_CONFIG["backend_url"])

def set_backend_url(url: str) -> None:
    config = load_config()
    config["backend_url"] = url
    save_config(config)

def get_output_format() -> str:
    return load_config().get("output_format", DEFAULT_CONFIG["output_format"])

def set_output_format(fmt: str) -> None:
    config = load_config()
    config["output_format"] = fmt
    save_config(config)

def get_timeout() -> int:
    return load_config().get("timeout", DEFAULT_CONFIG["timeout"])
```

- [ ] **Step 3: Update session.py to use ~/.config/tradecraft/**

```python
"""Session state for tradecraft CLI."""
import json
from pathlib import Path
from typing import Dict, Any, Optional

from cli_anything.tradecraft.core.config import CONFIG_DIR

SESSION_FILE = CONFIG_DIR / "session.json"

def _ensure() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

def load_session() -> Dict[str, Any]:
    _ensure()
    if SESSION_FILE.exists():
        try:
            return json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}

def save_session(data: Dict[str, Any]) -> None:
    _ensure()
    SESSION_FILE.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

def get(key: str, default: Any = None) -> Any:
    return load_session().get(key, default)

def set_key(key: str, value: Any) -> None:
    data = load_session()
    data[key] = value
    save_session(data)
```

- [ ] **Step 4: Update api_client.py to use updated config path**

The file stays the same — it already imports from `core.config`. Just verify the import path still works:
```python
from cli_anything.tradecraft.core.config import get_backend_url, get_timeout
```

- [ ] **Step 5: Create main.py — CLI entry point**

```python
"""TradeCraft CLI entry point.

Usage:
    tradecraft --help
    tradecraft --json health
    tradecraft strategy create "mean reversion on AAPL" --tickers AAPL
    tradecraft coach kpis --period 90
    tradecraft markov status
"""
import json
import os
import sys
from typing import Any, Optional

import click

from cli_anything.tradecraft.core.config import load_config
from cli_anything.tradecraft.core.export import emit


def _json_flag() -> bool:
    ctx = click.get_current_context()
    return ctx.obj.get("json", False) if ctx and ctx.obj else False

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
    """TradeCraft CLI — strategy creation, backtesting, coach analytics, Markov learning."""
    ctx.ensure_object(dict)
    ctx.obj["json"] = json_output
    ctx.obj["dry_run"] = dry_run
    if backend:
        os.environ["TRADECRAFT_BACKEND_URL"] = backend
    ctx.obj["config"] = load_config()


# Import and register command groups
from cli_anything.tradecraft.commands.health import health, db_status
from cli_anything.tradecraft.commands.sectors import sectors
from cli_anything.tradecraft.commands.screener import screener
from cli_anything.tradecraft.commands.quantgen import quantgen
from cli_anything.tradecraft.commands.strategies import strategies
from cli_anything.tradecraft.commands.strategy import strategy
from cli_anything.tradecraft.commands.coach import coach
from cli_anything.tradecraft.commands.markov import markov
from cli_anything.tradecraft.commands.projects import projects
from cli_anything.tradecraft.commands.config_cmd import config_cmd
from cli_anything.tradecraft.commands.repl import repl

cli.add_command(health)
cli.add_command(db_status)
cli.add_command(sectors)
cli.add_command(screener)
cli.add_command(quantgen)
cli.add_command(strategies)
cli.add_command(strategy)
cli.add_command(coach)
cli.add_command(markov)
cli.add_command(projects)
cli.add_command(config_cmd)
cli.add_command(repl)


def main():
    cli()

if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Create commands/__init__.py** (empty)

- [ ] **Step 7: Create commands/health.py**

```python
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
```

- [ ] **Step 8: Create commands/sectors.py**

```python
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
```

- [ ] **Step 9: Create commands/screener.py**

```python
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
```

- [ ] **Step 10: Create commands/quantgen.py**

```python
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
```

- [ ] **Step 11: Create commands/strategies.py**

```python
"""Strategy persistence commands."""
from pathlib import Path
from typing import Optional

import click
from cli_anything.tradecraft.utils.api_client import APIError, get as api_get, post as api_post, delete as api_delete
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
```

- [ ] **Step 12: Create commands/projects.py**

```python
"""Project management commands."""
import json
from pathlib import Path
from typing import Optional

import click
from cli_anything.tradecraft.utils.api_client import APIError, get as api_get, post as api_post, delete as api_delete
from cli_anything.tradecraft.main import _emit
from cli_anything.tradecraft.core.project import Project


@click.group()
def projects():
    """Local project grouping commands."""


@projects.command("create")
@click.argument("name")
@click.option("--description", help="Project description.")
def projects_create(name: str, description: Optional[str]):
    """Create a new project."""
    try:
        p = Project(name)
        p.create(description=description or "")
        _emit({"name": name, "description": description}, title="Project Created")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@projects.command("show")
@click.argument("name")
def projects_show(name: str):
    """Show project details."""
    try:
        p = Project(name)
        data = p.load()
        _emit(data, title=f"Project: {name}")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@projects.command("notes")
@click.argument("name")
@click.argument("notes_text", required=False)
def projects_notes(name: str, notes_text: Optional[str]):
    """Get or set project notes."""
    try:
        p = Project(name)
        if notes_text:
            p.add_notes(notes_text)
            click.echo("Notes saved.")
        else:
            data = p.load()
            click.echo(data.get("notes", ""))
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@projects.command("add-scan")
@click.argument("name")
@click.argument("scan_id")
def projects_add_scan(name: str, scan_id: str):
    """Associate a scan with a project."""
    try:
        p = Project(name)
        p.add_scan(scan_id)
        _emit({"project": name, "scan_id": scan_id}, title="Scan Added")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@projects.command("add-strategy")
@click.argument("name")
@click.argument("strategy_name")
def projects_add_strategy(name: str, strategy_name: str):
    """Associate a strategy with a project."""
    try:
        p = Project(name)
        p.add_strategy(strategy_name)
        _emit({"project": name, "strategy": strategy_name}, title="Strategy Added")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@projects.command("delete")
@click.argument("name")
def projects_delete(name: str):
    """Delete a project."""
    try:
        p = Project(name)
        p.delete()
        _emit({"name": name}, title="Project Deleted")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
```

- [ ] **Step 13: Create commands/config_cmd.py**

```python
"""Configuration commands."""
import click
from cli_anything.tradecraft.core.config import load_config, save_config, get_backend_url, set_backend_url, get_output_format, set_output_format
from cli_anything.tradecraft.main import _emit


@click.group(name="config")
def config_cmd():
    """CLI configuration commands."""


@config_cmd.command("show")
def config_show():
    """Show current configuration."""
    _emit(load_config(), title="Configuration")


@config_cmd.command("get")
@click.argument("key")
def config_get(key: str):
    """Get a config value."""
    config = load_config()
    if key in config:
        click.echo(f"{key}: {config[key]}")
    else:
        click.echo(f"Unknown key: {key}", err=True)
        raise SystemExit(1)


@config_cmd.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str):
    """Set a config value."""
    valid_keys = {"backend_url", "output_format", "timeout", "auto_save"}
    if key not in valid_keys:
        click.echo(f"Valid keys: {', '.join(sorted(valid_keys))}", err=True)
        raise SystemExit(1)
    config = load_config()
    if key == "timeout":
        config[key] = int(value)
    elif key == "auto_save":
        config[key] = value.lower() in ("true", "1", "yes")
    else:
        config[key] = value
    save_config(config)
    click.echo(f"{key} set to {config[key]}")
```

- [ ] **Step 14: Create commands/repl.py**

```python
"""Interactive REPL command."""
import click
from cli_anything.tradecraft.main import cli


@click.command()
@click.pass_context
def repl(ctx):
    """Start an interactive shell."""
    import shlex
    import sys
    try:
        import readline  # noqa: F401 — enables arrow key history
    except ImportError:
        pass
    click.echo("TradeCraft REPL. Type 'exit' or Ctrl+D to quit.")
    while True:
        try:
            line = input("tradecraft> ").strip()
        except (EOFError, KeyboardInterrupt):
            click.echo()
            break
        if not line or line in ("exit", "quit"):
            break
        try:
            cli.main(args=shlex.split(line), standalone_mode=False)
        except SystemExit:
            pass
        except Exception as e:
            click.echo(f"Error: {e}", err=True)
```

- [ ] **Step 15: Run tests to verify CLI loads**

```bash
cd agent-harness && pip install -e . 2>&1 | tail -3
tradecraft --help
```

Expected output: shows all command groups (health, db-status, sectors, screener, quantgen, strategies, strategy, coach, markov, projects, config, repl).

- [ ] **Step 16: Commit**

```bash
git add agent-harness/
git commit -m "feat(cli): rebuild tradecraft CLI with modular command structure

- New tradecraft entry point replacing cli-anything-tradecraft
- Config/session dir migrated to ~/.config/tradecraft/
- Commands split into separate files: health, sectors, screener,
  quantgen, strategies, strategy, coach, markov, projects, config, repl
- All commands support --json for machine-readable output

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: Strategy Lab — create, review, backtest, test-on, save, list, show

**Files:**
- Create: `agent-harness/cli_anything/tradecraft/commands/strategy.py`
- Create: `agent-harness/cli_anything/tradecraft/tests/test_strategy.py`

**Interfaces:**
- Consumes: `api_client.py` (get, post), `main.py` (_emit, _dry_run), `core/session.py` (set_key, get)
- Produces: `strategy` command group with create/review/backtest/test-on/save/list/show

- [ ] **Step 1: Create commands/strategy.py**

```python
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
        strategy_id = str(uuid.uuid4())[:8]
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
```

- [ ] **Step 2: Create tests/test_strategy.py**

```python
"""Tests for strategy commands."""
import json
import pytest
from click.testing import CliRunner
from cli_anything.tradecraft.main import cli


def test_strategy_create_missing_tickers():
    """Strategy create should fail without --tickers."""
    runner = CliRunner()
    result = runner.invoke(cli, ["strategy", "create", "test strategy"])
    assert result.exit_code != 0
    assert "--tickers" in result.output


def test_strategy_review_not_found():
    """Review of non-existent strategy should fail gracefully."""
    runner = CliRunner()
    result = runner.invoke(cli, ["strategy", "review", "nonexistent"])
    assert result.exit_code != 0
    assert "not found" in result.output


def test_strategy_backtest_not_found():
    """Backtest of non-existent strategy should fail gracefully."""
    runner = CliRunner()
    result = runner.invoke(cli, ["strategy", "backtest", "nonexistent"])
    assert result.exit_code != 0
    assert "not found" in result.output


def test_strategy_save_not_found():
    """Save of non-existent strategy should fail gracefully."""
    runner = CliRunner()
    result = runner.invoke(cli, ["strategy", "save", "nonexistent", "--name", "test"])
    assert result.exit_code != 0
    assert "not found" in result.output


def test_strategy_test_on_missing_tickers():
    """Test-on should fail without --tickers."""
    runner = CliRunner()
    result = runner.invoke(cli, ["strategy", "test-on", "some-id"])
    assert result.exit_code != 0
    assert "--tickers" in result.output


def test_strategy_list_help():
    """Strategy list should show help."""
    runner = CliRunner()
    result = runner.invoke(cli, ["strategy", "list", "--help"])
    assert result.exit_code == 0
    assert "--kind" in result.output
```

- [ ] **Step 3: Run tests**

```bash
cd agent-harness && python -m pytest cli_anything/tradecraft/tests/test_strategy.py -v
```

Expected: 6 passed.

- [ ] **Step 4: Commit**

```bash
git add agent-harness/cli_anything/tradecraft/commands/strategy.py agent-harness/cli_anything/tradecraft/tests/test_strategy.py
git commit -m "feat(cli): add strategy lab commands (create/review/backtest/test-on/save/list/show)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: Lessons Learned — capture, store, match, inject

**Files:**
- Create: `agent-harness/cli_anything/tradecraft/core/lessons.py`
- Create: `agent-harness/cli_anything/tradecraft/tests/test_lessons.py`

**Interfaces:**
- Consumes: `core/config.py` (CONFIG_DIR for file path)
- Produces: `LessonsStore` class with `add()`, `match()`, `all()`, `to_prompt()` methods

- [ ] **Step 1: Create core/lessons.py**

```python
"""Lessons learned store for code generation quality.

Captures strategy code generation errors and prevents repeats by
injecting relevant lessons into future LLM prompts.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from cli_anything.tradecraft.core.config import CONFIG_DIR

LESSONS_FILE = CONFIG_DIR / "lessons.json"

DEFAULT_LESSONS = [
    {
        "pattern": "vbt_comparison_operators",
        "error_sig": "cannot join with no overlapping index names",
        "fix": "Use .vbt.gt() / .vbt.lt() instead of > / <, and vbt.combine_logic instead of &",
        "trigger_hint": "VBT optimization",
        "count": 0,
        "first_seen": "",
        "last_seen": "",
    },
    {
        "pattern": "missing_broadcast_kwargs",
        "error_sig": "Portfolio.from_signals shape mismatch",
        "fix": "Add broadcast_kwargs={'keep_pd': True} to Portfolio.from_signals",
        "trigger_hint": "multi-ticker backtest",
        "count": 0,
        "first_seen": "",
        "last_seen": "",
    },
]


class LessonsStore:
    """Persistent store for code generation lessons learned."""

    def __init__(self):
        self._lessons: List[Dict[str, Any]] = []
        self._load()

    def _path(self) -> Path:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        return LESSONS_FILE

    def _load(self) -> None:
        path = self._path()
        if path.exists():
            try:
                self._lessons = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._lessons = list(DEFAULT_LESSONS)
        else:
            self._lessons = list(DEFAULT_LESSONS)
            self._save()

    def _save(self) -> None:
        self._path().write_text(
            json.dumps(self._lessons, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def add(self, error_sig: str, fix: str, pattern: str, trigger_hint: str = "") -> None:
        """Add or update a lesson. If error_sig matches an existing lesson, increment count."""
        now = datetime.now().isoformat()
        for lesson in self._lessons:
            if lesson["error_sig"] == error_sig or lesson["pattern"] == pattern:
                lesson["count"] += 1
                lesson["last_seen"] = now
                if fix:
                    lesson["fix"] = fix
                if trigger_hint:
                    lesson["trigger_hint"] = trigger_hint
                self._save()
                return
        self._lessons.append({
            "pattern": pattern,
            "error_sig": error_sig,
            "fix": fix,
            "trigger_hint": trigger_hint,
            "count": 1,
            "first_seen": now,
            "last_seen": now,
        })
        self._save()

    def match(self, error_text: str) -> Optional[Dict[str, Any]]:
        """Find a lesson whose error_sig appears in the error text."""
        error_lower = error_text.lower()
        for lesson in self._lessons:
            if lesson["error_sig"].lower() in error_lower:
                return lesson
        return None

    def all(self) -> List[Dict[str, Any]]:
        return list(self._lessons)

    def to_prompt(self, context_hint: str = "") -> str:
        """Generate a prompt suffix with relevant lessons.

        If context_hint is provided, only include lessons whose trigger_hint
        matches. Otherwise include all lessons with count > 0.
        """
        context_lower = context_hint.lower()
        relevant = []
        for lesson in self._lessons:
            if lesson["count"] == 0:
                continue
            if context_hint and lesson["trigger_hint"].lower() not in context_lower:
                continue
            relevant.append(lesson)

        if not relevant:
            return ""

        lines = ["\n## Known Pitfalls (from lessons learned)"]
        for lesson in relevant:
            lines.append(f"- {lesson['fix']}  (seen {lesson['count']}x)")
        return "\n".join(lines)
```

- [ ] **Step 2: Create tests/test_lessons.py**

```python
"""Tests for lessons learned store."""
import json
import tempfile
from pathlib import Path

import pytest

from cli_anything.tradecraft.core.lessons import LessonsStore


@pytest.fixture
def store(tmp_path: Path) -> LessonsStore:
    """Create a LessonsStore with a temp config dir."""
    import cli_anything.tradecraft.core.config as cfg
    original = cfg.CONFIG_DIR
    cfg.CONFIG_DIR = tmp_path / ".config" / "tradecraft"
    s = LessonsStore()
    yield s
    cfg.CONFIG_DIR = original


def test_default_lessons_exist(store: LessonsStore):
    """Store should have default lessons loaded."""
    all_lessons = store.all()
    assert len(all_lessons) >= 2
    patterns = [l["pattern"] for l in all_lessons]
    assert "vbt_comparison_operators" in patterns
    assert "missing_broadcast_kwargs" in patterns


def test_add_new_lesson(store: LessonsStore):
    """Adding a new lesson should append it."""
    store.add("some new error", "use X instead of Y", "new_pattern", "backtest")
    all_lessons = store.all()
    assert any(l["pattern"] == "new_pattern" for l in all_lessons)
    new = [l for l in all_lessons if l["pattern"] == "new_pattern"][0]
    assert new["count"] == 1
    assert new["first_seen"] == new["last_seen"]


def test_add_existing_lesson_increments_count(store: LessonsStore):
    """Adding a lesson with an existing error_sig should increment count."""
    store.add("cannot join with no overlapping index names", "", "vbt_comparison_operators")
    lesson = store.match("cannot join with no overlapping index names")
    assert lesson is not None
    assert lesson["count"] >= 1


def test_match_finds_lesson(store: LessonsStore):
    """Match should find a lesson by error signature substring."""
    lesson = store.match("cannot join with no overlapping index names")
    assert lesson is not None
    assert lesson["pattern"] == "vbt_comparison_operators"


def test_match_returns_none_for_unknown(store: LessonsStore):
    """Match should return None for unknown errors."""
    lesson = store.match("completely unknown error XYZ123")
    assert lesson is None


def test_to_prompt_empty_when_no_errors(store: LessonsStore):
    """to_prompt should return empty string when no lessons have been seen."""
    # Reset counts to 0
    for l in store.all():
        l["count"] = 0
    prompt = store.to_prompt()
    assert prompt == ""


def test_to_prompt_includes_relevant_lessons(store: LessonsStore):
    """to_prompt should include lessons matching context hint."""
    store.add("cannot join with no overlapping index names", "", "vbt_comparison_operators", "VBT optimization")
    prompt = store.to_prompt("VBT optimization")
    assert "vbt.combine_logic" in prompt
    assert "vbt_comparison_operators" not in prompt  # pattern name not in output


def test_to_prompt_filters_by_context(store: LessonsStore):
    """to_prompt should only include lessons matching context hint."""
    store.add("cannot join with no overlapping index names", "", "vbt_comparison_operators", "VBT optimization")
    prompt = store.to_prompt("screener scan")
    assert prompt == ""  # no match
```

- [ ] **Step 3: Run tests**

```bash
cd agent-harness && python -m pytest cli_anything/tradecraft/tests/test_lessons.py -v
```

Expected: 8 passed.

- [ ] **Step 4: Commit**

```bash
git add agent-harness/cli_anything/tradecraft/core/lessons.py agent-harness/cli_anything/tradecraft/tests/test_lessons.py
git commit -m "feat(cli): add lessons learned store for code generation quality

- LessonsStore with add/match/all/to_prompt methods
- Default lessons for known VBT pitfalls
- Persists to ~/.config/tradecraft/lessons.json
- Context-aware prompt generation for LLM injection

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: Coach Commands — kpis, report, trades CRUD

**Files:**
- Create: `agent-harness/cli_anything/tradecraft/commands/coach.py`
- Create: `agent-harness/cli_anything/tradecraft/tests/test_coach.py`

**Interfaces:**
- Consumes: `api_client.py` (get, post), `main.py` (_emit)
- Produces: `coach` command group with kpis/report/trades list/add/close

- [ ] **Step 1: Create commands/coach.py**

```python
"""Coach / Performance Analytics commands."""
from typing import Optional

import click
from cli_anything.tradecraft.utils.api_client import APIError, get as api_get, post as api_post
from cli_anything.tradecraft.main import _emit


@click.group()
def coach():
    """Performance analytics and coaching commands."""


@coach.command("kpis")
@click.option("--period", type=int, default=90, help="Analysis period in days (default: 90).")
@click.option("--strategy-id", help="Filter by strategy ID.")
def coach_kpis(period: int, strategy_id: Optional[str]):
    """Get key performance indicators from the trade journal."""
    params = {"period_days": period}
    if strategy_id:
        params["strategy_id"] = strategy_id
    try:
        data = api_get("/coach/kpis", params=params)
        _emit(data, title=f"KPIs (last {period}d)")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@coach.command("report")
@click.option("--period", type=int, default=90, help="Analysis period in days (default: 90).")
@click.option("--strategy-id", help="Filter by strategy ID.")
def coach_report(period: int, strategy_id: Optional[str]):
    """Get an LLM-generated critique report with recommendations."""
    params = {"period_days": period}
    if strategy_id:
        params["strategy_id"] = strategy_id
    try:
        data = api_get("/coach/report", params=params)
        _emit(data, title=f"Coach Report (last {period}d)")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@click.group(name="trades")
def coach_trades():
    """Trade journal CRUD commands."""


@coach_trades.command("list")
@click.option("--period", type=int, default=90, help="Filter by days (default: 90).")
@click.option("--strategy-id", help="Filter by strategy ID.")
def coach_trades_list(period: int, strategy_id: Optional[str]):
    """List trades from the journal."""
    params = {"period_days": period}
    if strategy_id:
        params["strategy_id"] = strategy_id
    try:
        data = api_get("/coach/trades", params=params)
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
        "notes": notes or "",
    }
    try:
        data = api_post("/coach/trades", body=body)
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
        data = api_post(f"/coach/trades/{trade_id}/close", body=body)
        _emit(data, title="Trade Closed")
    except APIError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


# Register trades sub-group under coach
coach.add_command(coach_trades)
```

- [ ] **Step 2: Create tests/test_coach.py**

```python
"""Tests for coach commands."""
from click.testing import CliRunner
from cli_anything.tradecraft.main import cli


def test_coach_kpis_help():
    """Coach kpis should show help."""
    runner = CliRunner()
    result = runner.invoke(cli, ["coach", "kpis", "--help"])
    assert result.exit_code == 0
    assert "--period" in result.output
    assert "--strategy-id" in result.output


def test_coach_report_help():
    """Coach report should show help."""
    runner = CliRunner()
    result = runner.invoke(cli, ["coach", "report", "--help"])
    assert result.exit_code == 0
    assert "--period" in result.output


def test_coach_trades_list_help():
    """Coach trades list should show help."""
    runner = CliRunner()
    result = runner.invoke(cli, ["coach", "trades", "list", "--help"])
    assert result.exit_code == 0
    assert "--period" in result.output


def test_coach_trades_add_missing_ticker():
    """Trades add should fail without --ticker."""
    runner = CliRunner()
    result = runner.invoke(cli, ["coach", "trades", "add"])
    assert result.exit_code != 0
    assert "--ticker" in result.output


def test_coach_trades_close_help():
    """Trades close should show help."""
    runner = CliRunner()
    result = runner.invoke(cli, ["coach", "trades", "close", "--help"])
    assert result.exit_code == 0
    assert "TRADE_ID" in result.output
```

- [ ] **Step 3: Run tests**

```bash
cd agent-harness && python -m pytest cli_anything/tradecraft/tests/test_coach.py -v
```

Expected: 5 passed.

- [ ] **Step 4: Commit**

```bash
git add agent-harness/cli_anything/tradecraft/commands/coach.py agent-harness/cli_anything/tradecraft/tests/test_coach.py
git commit -m "feat(cli): add coach commands (kpis, report, trades CRUD)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: Markov Commands — status, train, signal

**Files:**
- Create: `agent-harness/cli_anything/tradecraft/commands/markov.py`

**Interfaces:**
- Consumes: `api_client.py` (get, post), `main.py` (_emit)
- Produces: `markov` command group with status/train/signal

- [ ] **Step 1: Create commands/markov.py**

```python
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
```

- [ ] **Step 2: Verify CLI loads with markov commands**

```bash
cd agent-harness && tradecraft markov --help
```

Expected: shows status, train, signal subcommands.

- [ ] **Step 3: Commit**

```bash
git add agent-harness/cli_anything/tradecraft/commands/markov.py
git commit -m "feat(cli): add markov commands (status, train, signal)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 6: Claude Code Integration — tool registration + skill

**Files:**
- Create: `.claude/settings.json`
- Create: `.claude/skills/tradecraft/SKILL.md`

**Interfaces:**
- Consumes: the `tradecraft` CLI (must be installed as `pip install -e agent-harness/`)
- Produces: Claude Code tool registration and conversation orchestrator skill

- [ ] **Step 1: Create .claude/settings.json**

```json
{
  "tools": {
    "tradecraft": {
      "command": "tradecraft",
      "args": ["--json"],
      "description": "TradeCraft CLI — strategy creation, backtesting, coach analytics, Markov learning. Use for: creating/backtesting trading strategies from natural language, checking trading performance KPIs, getting coach reports, checking Markov model status, running sector rotation scans, AI stock screening, and QuantGen strategy generation."
    }
  }
}
```

- [ ] **Step 2: Create .claude/skills/tradecraft/SKILL.md**

```markdown
# TradeCraft Natural Language Strategy Lab

Use this skill when the user wants to create, backtest, analyze, or save trading strategies using natural language.

## Workflow

### Creating a Strategy

1. Call `tradecraft strategy create "<description>" --tickers <list>`
2. Present the summary and generated code to the user
3. Ask if they want to backtest it

### Backtesting

1. Call `tradecraft strategy backtest <id>`
2. Present metrics: total_return, win_rate, sharpe_ratio, max_drawdown, n_trades
3. Offer multi-asset testing: `tradecraft strategy test-on <id> --tickers <list>`
4. Offer to save: `tradecraft strategy save <id> --name "<name>"`

### Lessons Learned (Code Quality)

Before generating strategy code, check for relevant lessons:
1. Read `~/.config/tradecraft/lessons.json`
2. If lessons exist with `count > 0` matching the context, include them in the generation prompt as "known pitfalls to avoid"
3. After a failed backtest, capture the error and store it:
   - `tradecraft lessons add --error "<error>" --fix "<fix>" --pattern "<name>"`

### Checking Performance

- `tradecraft coach kpis --period 90` — get KPI dashboard
- `tradecraft coach report --period 90` — get LLM critique
- `tradecraft coach trades list` — see recent trades

### Markov Learning Agent

- `tradecraft markov status` — check model health
- `tradecraft markov signal <ticker>` — get conviction signal

## Output Format

All commands support `--json` for machine-readable output. Parse the JSON to extract metrics and present them conversationally to the user.
```

- [ ] **Step 3: Verify Claude Code discovers the tool**

```bash
# The tool should appear in Claude Code's tool list
# Verify by checking that tradecraft is on PATH
which tradecraft
tradecraft --help
```

Expected: `tradecraft` is found and shows all command groups.

- [ ] **Step 4: Commit**

```bash
git add .claude/settings.json .claude/skills/tradecraft/SKILL.md
git commit -m "feat(cli): add Claude Code integration (tool registration + skill)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Spec Coverage Check

| Spec Requirement | Task |
|---|---|
| Rebuild CLI from scratch | Task 1 |
| Strategy create/review/backtest/test-on/save/list/show | Task 2 |
| Lessons learned for code generation quality | Task 3 |
| Coach kpis/report/trades CRUD | Task 4 |
| Markov status/train/signal | Task 5 |
| Claude Code tool registration + skill | Task 6 |
| All commands support --json | Tasks 1-5 (built into _emit) |
| Config dir ~/.config/tradecraft/ | Task 1 (config.py) |
