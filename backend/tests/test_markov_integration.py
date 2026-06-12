"""Integration tests for Markov Chain Trader."""
import pytest
from app.services.markov.signal_provider import MarkovSignalProvider


def test_markov_provider_importable():
    """MarkovSignalProvider can be imported and instantiated."""
    provider = MarkovSignalProvider(model="xgboost")
    assert provider is not None
    assert provider.model == "xgboost"


def test_markov_provider_signal_contract():
    """Provider returns correct signal types."""
    provider = MarkovSignalProvider()
    signal = provider.get_signal('AAPL', '2024-01-15')
    assert signal in ('BUY', 'HOLD', 'SELL')


def test_markov_provider_conviction_contract():
    """Provider returns valid conviction range."""
    provider = MarkovSignalProvider()
    conviction = provider.get_conviction('AAPL', '2024-01-15')
    assert 0.0 <= conviction <= 1.0


def test_markov_provider_regime_contract():
    """Provider returns regime context."""
    provider = MarkovSignalProvider()
    regime = provider.get_regime('AAPL', '2024-01-15')
    assert 'regime' in regime
    assert 'bull_probability' in regime
    assert 'vol_regime' in regime