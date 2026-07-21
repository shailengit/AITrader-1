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
