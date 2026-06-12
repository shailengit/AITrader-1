"""End-to-end validation pipeline for Markov Chain Trader."""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from app.services.markov.regime_model import JumpModel, SectorRegimeManager
from app.services.markov.feature_engineering import (
    compute_log_returns, compute_rsi, compute_3day_forward_return,
    label_forward_return, compute_ticker_features,
)
from app.services.markov.pattern_recognizer import XGBoostRecognizer
from app.services.markov.signal_generator import SignalGenerator


def test_e2e_synthetic_regime_detection():
    """Step 1-2: Generate synthetic data with known regime shifts -> Jump Model finds them."""
    np.random.seed(42)
    # 300 days: first 150 bear (negative drift), last 150 bull (positive drift)
    bear = np.random.normal(-0.002, 0.01, 150)
    bull = np.random.normal(0.003, 0.008, 150)
    log_returns = np.concatenate([bear, bull])
    dates = pd.date_range('2023-01-01', periods=300, freq='B')
    features = pd.DataFrame({
        'log_return_20d': pd.Series(log_returns, index=dates),
        'downside_dev_10': pd.Series(np.abs(log_returns) * 0.5, index=dates),
        'downside_dev_20': pd.Series(np.abs(log_returns) * 0.5, index=dates),
        'sortino_20': pd.Series(log_returns * 2, index=dates),
        'sortino_60': pd.Series(log_returns * 2, index=dates),
    })

    model = JumpModel('SPY', jump_penalty=10.0)
    success = model.train(features)
    assert success, "Jump Model must train on synthetic data"

    # Verify regime detection
    regime = model.get_regime()
    assert regime['regime'] in ('BULL', 'BEAR'), "Must detect a regime"
    assert 0 <= regime['bull_probability'] <= 1, "Probability must be valid"

    # Last 150 days are bull -> should detect bull
    last_regime = model.get_regime(dates[-1].strftime('%Y-%m-%d'))
    assert last_regime['regime'] == 'BULL', "Last 150 days have positive drift -> BULL"


def test_e2e_convergent_signal_logic():
    """Step 4: Convergent signal rules produce correct outputs."""
    rm = SectorRegimeManager()
    gen = SignalGenerator(rm)

    # Manually set a bull regime
    model = JumpModel('XLK')
    model._is_trained = True
    model.garch_result = None
    model._smoothed_probs = pd.DataFrame({
        'bull_probability': pd.Series([0.9]),
        'regime': pd.Series([1.0]),
    }, index=pd.DatetimeIndex(['2026-06-11']))
    rm.models['XLK'] = model

    features = pd.Series({'f1': 0.5, 'f2': 0.5})
    result = gen.generate_signal('AAPL', 'Technology', features, model='xgboost', min_conviction=0.6)
    assert result['signal'] in ('BUY', 'HOLD', 'SELL'), "Signal must be valid"
    assert result['etf'] == 'XLK', "Technology maps to XLK"


def test_e2e_backtest_signal_provider():
    """Step 5-6: MarkovSignalProvider produces consistent signals."""
    from app.services.markov.signal_provider import MarkovSignalProvider
    provider = MarkovSignalProvider(model="xgboost")
    signal = provider.get_signal('AAPL', '2024-01-15')
    assert signal in ('BUY', 'HOLD', 'SELL')
    conviction = provider.get_conviction('AAPL', '2024-01-15')
    assert 0 <= conviction <= 1