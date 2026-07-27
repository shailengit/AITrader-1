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
