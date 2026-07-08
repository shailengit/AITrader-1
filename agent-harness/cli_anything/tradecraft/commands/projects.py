"""Project management commands."""
from typing import Optional

import click
from cli_anything.tradecraft.utils.api_client import APIError, get as api_get, post as api_post, delete as api_delete
from cli_anything.tradecraft.main import _emit
from cli_anything.tradecraft.core.project import Project


_PROJECT_HELP = (
    "The Project class in core/project.py does not yet implement this method. "
    "Update core/project.py with the required method to enable this command."
)


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
    except AttributeError:
        click.echo(f"Error: {_PROJECT_HELP}", err=True)
        raise SystemExit(1)
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
    except AttributeError:
        click.echo(f"Error: {_PROJECT_HELP}", err=True)
        raise SystemExit(1)
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
    except AttributeError:
        click.echo(f"Error: {_PROJECT_HELP}", err=True)
        raise SystemExit(1)
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
    except AttributeError:
        click.echo(f"Error: {_PROJECT_HELP}", err=True)
        raise SystemExit(1)
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
    except AttributeError:
        click.echo(f"Error: {_PROJECT_HELP}", err=True)
        raise SystemExit(1)
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
    except AttributeError:
        click.echo(f"Error: {_PROJECT_HELP}", err=True)
        raise SystemExit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
