"""Tests for signal generator."""
import pytest
import pandas as pd
import numpy as np
from app.services.markov.signal_generator import SignalGenerator
from app.services.markov.regime_model import SectorRegimeManager


def test_signal_generator_unknown_regime():
    manager = SectorRegimeManager()
    gen = SignalGenerator(manager)
    features = pd.Series({'f1': 0.5, 'f2': 0.5})
    result = gen.generate_signal('AAPL', 'Technology', features)
    assert result['ticker'] == 'AAPL'
    assert result['signal'] == 'HOLD'
    assert result['regime'] == 'UNKNOWN'


def test_signal_generator_bull_regime_hold_low_conviction():
    """In bull regime but low conviction → HOLD."""
    manager = SectorRegimeManager()
    gen = SignalGenerator(manager)

    # Manually set a bull regime for testing
    from app.services.markov.regime_model import JumpModel
    model = JumpModel('XLK')
    model._is_trained = True
    model.garch_result = None
    model._smoothed_probs = pd.DataFrame({
        'bull_probability': pd.Series([0.9]),
        'regime': pd.Series([1.0]),
    }, index=pd.DatetimeIndex(['2026-06-11']))
    manager.models['XLK'] = model

    features = pd.Series({'f1': 0.5, 'f2': 0.5})
    result = gen.generate_signal('AAPL', 'Technology', features, min_conviction=0.9)
    # Regime is BULL but recognizer not trained → HOLD
    assert result['signal'] == 'HOLD'


def test_scan_tickers_empty():
    manager = SectorRegimeManager()
    gen = SignalGenerator(manager)
    result = gen.scan_tickers([], model="xgboost")
    assert result['total_scanned'] == 0
    assert result['signals'] == []


def test_scan_tickers_sorts_by_conviction():
    manager = SectorRegimeManager()
    gen = SignalGenerator(manager)
    tickers = [{'ticker': 'AAPL', 'sector': 'Technology'}]
    result = gen.scan_tickers(tickers, max_results=10)
    assert result['total_scanned'] == 1
    assert isinstance(result['signals'], list)
