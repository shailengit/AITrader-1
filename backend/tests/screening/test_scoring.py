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


def test_base_setup_default_weights_match_legacy_behavior():
    """When sub_weights is None, the total uses 30/25/20/25 hard-coded."""
    row = _row()
    default = compute_base_setup_breakdown(row)['total']
    explicit = compute_base_setup_breakdown(row, sub_weights={'trend': 30, 'momentum': 25, 'volatility': 20, 'volume': 25})['total']
    assert math.isclose(default, explicit, abs_tol=0.05)


def test_base_setup_user_weights_change_total():
    """Larger weight on trend shifts the total toward the trend sub-score."""
    # Use a row where the sub-scores are not all equal so the weight swap is observable.
    # With close > SMA20 > SMA50 + MACD>0 + high ADX, trend_score ~ 95-100.
    # With RSI 30 (oversold) + ROC -10, momentum_score is depressed.
    row = _row(
        trend_adx=55.0,
        trend_sma_fast=99.0,
        trend_sma_slow=95.0,
        close=101.0,
        trend_macd_diff=1.5,
        momentum_rsi=30.0,
        momentum_roc=-10.0,
    )
    trend_heavy = compute_base_setup_breakdown(row, sub_weights={'trend': 100, 'momentum': 0, 'volatility': 0, 'volume': 0})['total']
    momentum_heavy = compute_base_setup_breakdown(row, sub_weights={'trend': 0, 'momentum': 100, 'volatility': 0, 'volume': 0})['total']
    assert trend_heavy > momentum_heavy


def test_base_setup_all_zero_weights_falls_back_to_equal():
    """All-zero weights must not raise; fallback uses equal weights."""
    row = _row()
    out = compute_base_setup_breakdown(row, sub_weights={'trend': 0, 'momentum': 0, 'volatility': 0, 'volume': 0})
    assert 0 <= out['total'] <= 100


def test_base_setup_score_forwards_sub_weights():
    """compute_base_setup_score must accept and forward sub_weights."""
    row = _row()
    default = compute_base_setup_score(row)
    explicit = compute_base_setup_score(row, sub_weights={'trend': 30, 'momentum': 25, 'volatility': 20, 'volume': 25})
    assert math.isclose(default, explicit, abs_tol=0.05)


def test_compute_quant_score_returns_dict_with_score_only_by_default():
    """When include_alignment is False (default), the result is a dict with only `score`."""
    filters = {}
    out = compute_quant_score(_row(), filters)
    assert isinstance(out, dict)
    assert 'score' in out
    assert 'score_minus_return' not in out


def test_compute_quant_score_with_alignment_returns_both_keys():
    """When include_alignment is True and the row has return_pct, both keys are present."""
    filters = {}
    row = _row()
    row['return_pct'] = 5.0
    out = compute_quant_score(row, filters, include_alignment=True)
    assert 'score' in out
    assert 'score_minus_return' in out
    # 5% return is normalized to 5; score_minus_return = score - 5
    assert math.isclose(out['score_minus_return'], out['score'] - 5.0, abs_tol=0.5)


def test_compute_quant_score_alignment_clamps_extreme_returns():
    """Return values outside [-100, 100] are clamped before subtraction."""
    row = _row()
    row['return_pct'] = 250.0
    out = compute_quant_score(row, {}, include_alignment=True)
    assert math.isclose(out['score_minus_return'], out['score'] - 100.0, abs_tol=0.5)
    row['return_pct'] = -300.0
    out = compute_quant_score(row, {}, include_alignment=True)
    assert math.isclose(out['score_minus_return'], out['score'] + 100.0, abs_tol=0.5)


def test_compute_quant_score_alignment_skipped_when_no_return_pct():
    """Without return_pct, score_minus_return is omitted even if alignment is on."""
    row = _row()
    out = compute_quant_score(row, {}, include_alignment=True)
    assert 'score_minus_return' not in out


def test_scan_request_accepts_sub_weights():
    """The ScanRequest model accepts a valid sub_weights dict."""
    from app.routers.screener import ScanRequest
    req = ScanRequest(
        mode='quant_strategy',
        sub_weights={'trend': 50, 'momentum': 25, 'volatility': 10, 'volume': 15},
        include_alignment=True,
    )
    assert req.sub_weights == {'trend': 50, 'momentum': 25, 'volatility': 10, 'volume': 15}
    assert req.include_alignment is True


def test_scan_request_sub_weights_default_to_none():
    """When omitted, sub_weights is None and include_alignment is False."""
    from app.routers.screener import ScanRequest
    req = ScanRequest(mode='quant_strategy')
    assert req.sub_weights is None
    assert req.include_alignment is False


# ── Cross bonus branch (defence in depth for the crossed_above filter) ──

def test_cross_bonus_is_100_when_cross_happened():
    """A `crossed_above` filter whose worker-evaluated boolean is True should
    give a bonus of 100. A False boolean should give 0. Multiple filters
    should be averaged."""
    from app.services.screening.scoring import compute_filter_match_bonus

    cross_col = 'cross_sma_50_crossed_above_sma_200_in_1d'
    filters = {
        'indicator_filters': [{
            'column': 'sma_50',
            'condition': 'crossed_above',
            'reference_column': 'sma_200',
            'lookback_days': 1,
        }]
    }
    # The worker would have attached the boolean column to the row.
    row_true = _row(**{cross_col: True})
    row_false = _row(**{cross_col: False})
    assert compute_filter_match_bonus(row_true, filters) == 100.0
    assert compute_filter_match_bonus(row_false, filters) == 0.0


def test_cross_bonus_coexists_with_legacy_filter():
    """A cross + a legacy min/max filter should be averaged, not overridden."""
    from app.services.screening.scoring import compute_filter_match_bonus

    cross_col = 'cross_sma_50_crossed_above_sma_200_in_1d'
    filters = {
        'indicator_filters': [
            {
                'column': 'sma_50',
                'condition': 'crossed_above',
                'reference_column': 'sma_200',
                'lookback_days': 1,
            },
            {'column': 'momentum_rsi', 'min': 30},  # row has RSI=55, well above 30
        ]
    }
    row = _row(**{cross_col: True})  # default _row has RSI=55
    bonus = compute_filter_match_bonus(row, filters)
    # Cross branch: 100, RSI branch: ~71 → averaged → ~85
    assert 80 < bonus < 90, f"expected ~85, got {bonus}"


def test_cross_bonus_handles_missing_boolean_column():
    """If the cross boolean column is not on the row (worker didn't run or
    column not requested), the function should not crash; it should fall
    through to legacy logic, which finds no min/max and no usable column,
    so no bonuses are appended and the function returns the neutral 50.0
    (`compute_filter_match_bonus` returns 50.0 when no bonuses are
    collected)."""
    from app.services.screening.scoring import compute_filter_match_bonus

    filters = {
        'indicator_filters': [{
            'column': 'sma_50',
            'condition': 'crossed_above',
            'reference_column': 'sma_200',
            'lookback_days': 1,
        }]
    }
    # No cross column on the row, no sma_50 either
    row = _row()
    del row['trend_sma_fast']  # so the cross branch's `col in row.index` check is also false
    bonus = compute_filter_match_bonus(row, filters)
    # No bonuses collected → neutral 50.0 (not 0, not 100)
    assert bonus == 50.0
