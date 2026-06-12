"""Tests for MarkovSignalProvider."""
import pytest
from app.services.markov.signal_provider import MarkovSignalProvider


def test_provider_initial_state():
    provider = MarkovSignalProvider(model="xgboost")
    assert provider.model == "xgboost"
    assert provider.min_conviction == 0.6
    assert provider.strict is False
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


def test_provider_strict_mode_raises():
    """Strict mode returns None for missing dates."""
    provider = MarkovSignalProvider(strict=True)
    # Manually populate cache with one entry
    provider._cache['xgboost_AAPL'] = {'2024-01-10': {
        'signal': 'BUY', 'conviction': 0.8,
        'regime': 'BULL', 'bull_probability': 0.9,
        'vol_regime': 'LOW', 'vol_probability': 0.1, 'etf': 'XLK',
    }}
    entry = provider._get_entry('AAPL', '2024-01-15')
    assert entry is None, "Strict mode should reject missing dates"


def test_provider_populated_cache_hit():
    """Lookup from a pre-populated cache returns correct values."""
    provider = MarkovSignalProvider()
    provider._cache['xgboost_AAPL'] = {'2024-01-10': {
        'signal': 'BUY', 'conviction': 0.8,
        'regime': 'BULL', 'bull_probability': 0.9,
        'vol_regime': 'LOW', 'vol_probability': 0.1, 'etf': 'XLK',
    }}
    assert provider.get_signal('AAPL', '2024-01-10') == 'BUY'
    assert provider.get_conviction('AAPL', '2024-01-10') == 0.8
    regime = provider.get_regime('AAPL', '2024-01-10')
    assert regime['regime'] == 'BULL'
    assert regime['bull_probability'] == 0.9


def test_provider_populated_cache_fallback():
    """Missing date falls back to last known date when not strict."""
    provider = MarkovSignalProvider(strict=False)
    provider._cache['xgboost_AAPL'] = {'2024-01-10': {
        'signal': 'BUY', 'conviction': 0.8,
        'regime': 'BULL', 'bull_probability': 0.9,
        'vol_regime': 'LOW', 'vol_probability': 0.1, 'etf': 'XLK',
    }}
    # Date not in cache but cache has entries → falls back
    assert provider.get_signal('AAPL', '2024-01-15') == 'BUY'


def test_provider_empty_cache():
    """Empty cache returns HOLD/0.0/UNKNOWN."""
    provider = MarkovSignalProvider()
    assert provider.get_signal('AAPL', '2024-01-15') == 'HOLD'
    assert provider.get_conviction('AAPL', '2024-01-15') == 0.0
    regime = provider.get_regime('AAPL', '2024-01-15')
    assert regime['regime'] == 'UNKNOWN'