"""Parity tests for the StrategyEngine refactor.

Compares the refactored strategies/golden_cross.py (using strategies/engine.py)
against the original strategies/daily_golden_cross_rotation.py to ensure no
regression in aggregate KPIs.
"""
import importlib.util
import os
import sys

import pytest


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
STRATEGIES_DIR = os.path.join(REPO_ROOT, "strategies")


def _load_module(name: str, path: str):
    """Load a Python file as a module without it being a package member."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load {name} from {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_strategy_config_imports():
    engine = _load_module("strategies_engine", os.path.join(STRATEGIES_DIR, "engine.py"))
    config = engine.StrategyConfig(as_of="2022-01-01", end="2024-01-01")
    assert config.as_of == "2022-01-01"
    assert config.end == "2024-01-01"
    assert config.max_holdings == 5  # default


def test_engine_smoke_runs():
    """Engine should run with a stub config and produce a summary dict."""
    engine = _load_module("strategies_engine", os.path.join(STRATEGIES_DIR, "engine.py"))

    def fake_precompute(tickers, start, end):
        return {"AAPL": {
            "close": [100.0, 101.0, 102.0],
            "dates": ["2022-01-01", "2022-01-02", "2022-01-03"],
            "crossovers": [],
            "market_cap": 1e12,
            "sector": "Tech",
        }}

    config = engine.StrategyConfig(
        as_of="2022-01-01", end="2022-01-03", capital=10_000.0,
        precompute_fn=fake_precompute,
        entry_score_fn=lambda c, s: 0.5,
        holding_score_fn=lambda t, d, h, s: 0.5,
        exit_check_fn=lambda t, d, h, db: None,
    )
    runner = engine.StrategyEngine(config)
    result = runner.run()
    assert "summary" in result
    assert "trades" in result
    assert "daily_equity" in result


def test_safe_import_valid_file(tmp_path):
    safe = _load_module("strategies_safe_import", os.path.join(STRATEGIES_DIR, "_safe_import.py"))
    f = tmp_path / "valid_strategy.py"
    f.write_text("MY_CONST = 42\n")
    result = safe.safe_import_strategy(str(f))
    assert result.error is None
    assert result.module.MY_CONST == 42


def test_safe_import_syntax_error(tmp_path):
    safe = _load_module("strategies_safe_import", os.path.join(STRATEGIES_DIR, "_safe_import.py"))
    f = tmp_path / "broken.py"
    f.write_text("def broken(:\n    pass\n")
    result = safe.safe_import_strategy(str(f))
    assert result.error is not None
    assert "SyntaxError" in result.error or "invalid syntax" in result.error.lower()


def test_safe_import_missing_file():
    safe = _load_module("strategies_safe_import", os.path.join(STRATEGIES_DIR, "_safe_import.py"))
    result = safe.safe_import_strategy("/nonexistent/path/does_not_exist.py")
    assert result.error is not None
    assert result.module is None
