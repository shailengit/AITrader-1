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
