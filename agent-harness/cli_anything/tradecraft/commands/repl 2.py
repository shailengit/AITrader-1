"""Interactive REPL command."""
import click


@click.command()
@click.pass_context
def repl(ctx):
    """Start an interactive shell."""
    from cli_anything.tradecraft.main import cli
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
