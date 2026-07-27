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
