"""Tests for the screener scoring math."""
import math
import pandas as pd
from app.services.screening.scoring import (
    compute_base_setup_breakdown,
    compute_base_setup_score,
    compute_quant_score,
)


def _row(**kwargs):
    """Build a minimal row Series with the indicator columns the scoring needs."""
    base = {
        'close': 100.0,
        'trend_adx': 25.0,
        'trend_sma_fast': 99.0,
        'trend_sma_slow': 95.0,
        'trend_macd_diff': 0.5,
        'momentum_rsi': 55.0,
        'momentum_roc': 2.0,
        'momentum_stoch': 50.0,
        'volatility_atr': 3.0,
        'volatility_bbw': 8.0,
        'volume_ratio': 1.2,
        'volume_mfi': 60.0,
    }
    base.update(kwargs)
    return pd.Series(base)


def test_momentum_score_rsi_peak_is_65():
    """RSI 65 yields the highest rsi component. With ROC=0 and Stoch=55 the
    contribution from RSI dominates. RSI 65 should give 85 (rsi=100*0.45 +
    roc=50*0.30 + stoch=100*0.25 = 45 + 15 + 25 = 85). RSI 30 should give
    40 (rsi=0 + roc=15 + stoch=25)."""
    r65 = compute_base_setup_breakdown(_row(momentum_rsi=65.0, momentum_roc=0.0, momentum_stoch=55.0))['momentum_score']
    r30 = compute_base_setup_breakdown(_row(momentum_rsi=30.0, momentum_roc=0.0, momentum_stoch=55.0))['momentum_score']
    r100 = compute_base_setup_breakdown(_row(momentum_rsi=100.0, momentum_roc=0.0, momentum_stoch=55.0))['momentum_score']
    assert math.isclose(r65, 85.0, abs_tol=0.5)
    assert math.isclose(r30, 40.0, abs_tol=0.5)
    assert math.isclose(r100, 40.0, abs_tol=0.5)
    assert r65 > r30
    assert r65 > r100


def test_momentum_score_roc_negative_lowers_score():
    """Negative ROC drags momentum_score below the no-ROC baseline."""
    neutral = compute_base_setup_breakdown(_row(momentum_roc=0.0))['momentum_score']
    neg = compute_base_setup_breakdown(_row(momentum_roc=-10.0))['momentum_score']
    pos = compute_base_setup_breakdown(_row(momentum_roc=10.0))['momentum_score']
    assert pos > neutral > neg


def test_momentum_score_stoch_peak_is_55():
    """Stoch 55 yields the highest stoch_score within the formula."""
    s55 = compute_base_setup_breakdown(_row(momentum_stoch=55.0))['momentum_score']
    s10 = compute_base_setup_breakdown(_row(momentum_stoch=10.0))['momentum_score']
    assert s55 > s10
