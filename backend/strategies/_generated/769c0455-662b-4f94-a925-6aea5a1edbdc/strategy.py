import importlib.util, os, sys
import pandas as pd
import numpy as np

# Configure DB
os.environ.setdefault("DB_USER", "postgres")
os.environ.setdefault("DB_PASSWORD", "sarina00")
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "5431")
os.environ.setdefault("DB_NAME", "sp1500_1d")

# Load engine
_engine_path = os.path.join(os.path.dirname(__file__), "..", "..", "engine.py")
_spec = importlib.util.spec_from_file_location("engine_inline", _engine_path)
_engine = importlib.util.module_from_spec(_spec)
sys.modules["engine_inline"] = _engine
_spec.loader.exec_module(_engine)

# Load golden_cross for the proven implementation
import importlib.util
_gc_path = os.path.join(os.path.dirname(__file__), "..", "..", "golden_cross.py")
_spec_gc = importlib.util.spec_from_file_location("golden_cross_inline", _gc_path)
_gc = importlib.util.module_from_spec(_spec_gc)
sys.modules["golden_cross_inline"] = _gc
_spec_gc.loader.exec_module(_gc)

def precompute(tickers, start, end):
    return _gc.precompute(tickers, start, end)

def entry_score(candidate, stats):
    return _gc.entry_score(candidate, stats)

def holding_score(ticker, date_str, holding, stats):
    return _gc.holding_score(ticker, date_str, holding, stats)

def exit_check(ticker, date_str, holding, stock_db):
    return _gc.exit_check(ticker, date_str, holding, stock_db)


def build_config(as_of=None, end=None, capital=None):
    return _engine.StrategyConfig(
        as_of=as_of or "2022-01-01",
        end=end or "2024-01-01",
        capital=capital or 100_000.0,
        max_holdings=5, min_hold_days=7,
        trailing_stop=0.20, take_profit=0.30, time_stop_days=60,
        max_volatility=0.05, max_sector_count=2,
        bull_exposure=1.0, bear_exposure=0.50,
        precompute_fn=precompute, entry_score_fn=entry_score,
        holding_score_fn=holding_score, exit_check_fn=exit_check,
        name="test",
    )
