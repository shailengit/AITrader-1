"""Tests for MarkovSignalProvider."""
import pytest
from app.services.markov.signal_provider import MarkovSignalProvider


def test_provider_initial_state():
    provider = MarkovSignalProvider(model="xgboost")
    assert provider.model == "xgboost"
    signal = provider.get_signal('AAPL', '2024-01-15')
    assert signal == 'HOLD'
    conviction = provider.get_conviction('AAPL', '2024-01-15')
    assert conviction == 0.0


def test_provider_regime_unknown_ticker():
    provider = MarkovSignalProvider()
    regime = provider.get_regime('UNKNOWN', '2024-01-15')
    assert regime['regime'] == 'UNKNOWN'


def test_provider_cache_key():
    provider = MarkovSignalProvider(model="xgboost")
    key = provider._cache_key('AAPL')
    assert key == 'xgboost_AAPL'