"""Tests for regime model module."""
import pytest
import pandas as pd
import numpy as np
from app.services.markov.regime_model import JumpModel, SectorRegimeManager


def test_jump_model_initial_state():
    model = JumpModel('XLK', jump_penalty=10.0)
    assert model.etf_ticker == 'XLK'
    assert not model.is_trained
    regime = model.get_regime()
    assert regime['regime'] == 'UNKNOWN'


def test_jump_model_train_synthetic():
    """Train on synthetic data with known regime shift."""
    np.random.seed(42)
    # 200 days: first 100 in bear (negative drift), last 100 in bull (positive drift)
    bear_returns = np.random.normal(-0.001, 0.01, 100)
    bull_returns = np.random.normal(0.002, 0.008, 100)
    log_returns = np.concatenate([bear_returns, bull_returns])

    dates = pd.date_range('2023-01-01', periods=200, freq='B')
    features = pd.DataFrame({
        'log_return_20d': pd.Series(log_returns, index=dates),
        'downside_dev_10': pd.Series(np.abs(log_returns) * 0.5, index=dates),
        'downside_dev_20': pd.Series(np.abs(log_returns) * 0.5, index=dates),
        'sortino_20': pd.Series(log_returns * 2, index=dates),
        'sortino_60': pd.Series(log_returns * 2, index=dates),
    })

    model = JumpModel('SPY', jump_penalty=10.0)
    success = model.train(features)
    assert success
    assert model.is_trained

    regime = model.get_regime()
    assert regime['regime'] in ('BULL', 'BEAR')
    assert 0 <= regime['bull_probability'] <= 1
    assert regime['vol_regime'] in ('LOW', 'HIGH', 'UNKNOWN')


def test_jump_model_insufficient_data():
    model = JumpModel('XLK')
    features = pd.DataFrame({'log_return_20d': [0.01] * 10})
    success = model.train(features)
    assert not success


def test_sector_regime_manager():
    manager = SectorRegimeManager()
    assert len(manager.models) == 0
    assert manager.last_updated is None

    # Test get_regime for untrained ETF
    regime = manager.get_regime('XLK')
    assert regime['regime'] == 'UNKNOWN'


def test_get_ticker_regime_unknown_sector():
    manager = SectorRegimeManager()
    regime = manager.get_ticker_regime('AAPL', 'UnknownSector')
    assert regime['regime'] == 'UNKNOWN'
