"""
Scoring functions for Quant Strategy screening.
Extracted from agno_screener.py for better maintainability.
"""

import logging
from typing import Dict, Any, Optional

import pandas as pd

# Imported lazily inside `compute_filter_match_bonus` to avoid a circular
# import: `agno_screener` already imports from `screening.scoring`, so we
# can't `from app.services.agno_screener import _cross_column_name` at
# module load time. See function docstring for details.
_CROSS_COLUMN_NAME = None

logger = logging.getLogger(__name__)

def compute_base_setup_breakdown(row: pd.Series, sub_weights: Optional[Dict[str, int]] = None) -> Dict[str, float]:
    """Compute 0-100 sub-scores for each base-setup category.

    Returns dict with:
    - trend_score, momentum_score, volatility_score, volume_score, total
    """
    close = row.get('close', 0) or 1

    # --- Trend Strength ---
    adx = row.get('trend_adx', 0)
    adx_score = min(100, adx * 2) if adx > 0 else 0
    sma_fast = row.get('trend_sma_fast', 0)
    sma_slow = row.get('trend_sma_slow', 0)
    close_val = row.get('close', 0)
    if close_val > sma_fast > sma_slow:
        sma_score = 100
    elif close_val > sma_fast:
        sma_score = 70
    elif close_val > sma_slow:
        sma_score = 40
    else:
        sma_score = 0
    macd_diff = row.get('trend_macd_diff', 0)
    macd_score = 100 if macd_diff and macd_diff > 0 else 0
    trend_score = round(adx_score * 0.40 + sma_score * 0.35 + macd_score * 0.25, 1)

    # --- Momentum Quality ---
    # Peak at RSI 65 (strong with room to run), zero at RSI 30 and 100.
    # ROC contributes directionally — negative ROC subtracts, positive adds.
    # Stoch peak at 55, zero at 10 and 100.
    rsi = row.get('momentum_rsi', 50)
    rsi_score = 100 - min(abs(rsi - 65), 35) * (100 / 35)
    roc = row.get('momentum_roc', 0)
    roc_score = 50 + max(-50, min(50, roc * 5))
    stoch = row.get('momentum_stoch', 50)
    stoch_score = 100 - min(abs(stoch - 55), 45) * (100 / 45) if stoch is not None else 50
    momentum_score = round(rsi_score * 0.45 + roc_score * 0.30 + stoch_score * 0.25, 1)

    # --- Volatility Regime ---
    atr = row.get('volatility_atr', 0)
    atr_pct = (atr / close * 100) if close > 0 else 0
    if 1.0 <= atr_pct <= 5.0:
        atr_score = 100
    elif atr_pct < 1.0:
        atr_score = max(0, atr_pct * 100)
    elif atr_pct <= 10.0:
        atr_score = max(0, 100 - (atr_pct - 5.0) * 10)
    else:
        atr_score = max(0, 50 - (atr_pct - 10.0) * 5)
    bbw = row.get('volatility_bbw', 15)
    if 2.0 <= bbw <= 15.0:
        bbw_score = 100
    elif bbw < 2.0:
        bbw_score = max(0, 50 + bbw * 25)
    elif bbw <= 25.0:
        bbw_score = max(0, 100 - (bbw - 15.0) * 5)
    else:
        bbw_score = max(0, 50 - (bbw - 25.0) * 3)
    volatility_score = round(atr_score * 0.50 + bbw_score * 0.50, 1)

    # --- Volume Confirmation ---
    vol_ratio = row.get('volume_ratio', 1.0)
    if vol_ratio < 0.5:
        vol_ratio_score = 20
    elif vol_ratio < 1.0:
        vol_ratio_score = 60
    elif vol_ratio < 2.0:
        vol_ratio_score = 100
    elif vol_ratio < 5.0:
        vol_ratio_score = 80
    else:
        vol_ratio_score = 60
    mfi = row.get('volume_mfi', 50)
    mfi_score = min(mfi, 100) if mfi >= 50 else mfi * 2
    volume_score = round(vol_ratio_score * 0.50 + mfi_score * 0.50, 1)

    # Apply user-supplied sub-weights. Missing keys fall back to legacy
    # hard-coded values; all-zero weights fall back to equal weighting
    # to avoid division by zero.
    default_sub_weights = {'trend': 30, 'momentum': 25, 'volatility': 20, 'volume': 25}
    weights = {**default_sub_weights, **(sub_weights or {})}
    weight_sum = sum(weights.values())
    if weight_sum == 0:
        weights = {k: 1 for k in default_sub_weights}
        weight_sum = sum(weights.values())
    total = round(
        (trend_score * weights['trend']
         + momentum_score * weights['momentum']
         + volatility_score * weights['volatility']
         + volume_score * weights['volume']) / weight_sum,
        1,
    )

    return {
        'trend_score': trend_score,
        'momentum_score': momentum_score,
        'volatility_score': volatility_score,
        'volume_score': volume_score,
        'total': total,
    }


def compute_base_setup_score(row: pd.Series, sub_weights: Optional[Dict[str, int]] = None) -> float:
    """Compute a 0-100 base setup score from technical indicators."""
    return compute_base_setup_breakdown(row, sub_weights)['total']


def compute_filter_match_bonus(row: pd.Series, filters: Dict[str, Any]) -> float:
    """Compute 0-100 bonus for how strongly the stock satisfies user filters.

    For each indicator filter:
    - min filter: if actual >= min, score = 50 + (actual-min)/(max_possible-min)*50
    - max filter: if actual <= max, score = 50 + (max-actual)/(max-min_possible)*50
    - Average across all filters
    """
    bonuses = []
    indicator_filters = filters.get('indicator_filters', [])

    # Reference ranges for common indicators (used to scale the bonus)
    ref_ranges = {
        'momentum_rsi': (0, 100),
        'momentum_stoch': (0, 100),
        'momentum_wr': (-100, 0),
        'momentum_roc': (-50, 50),
        'momentum_tsi': (-100, 100),
        'momentum_ao': (-10, 10),
        'momentum_kama': (0, 1000),
        'volatility_bbw': (0, 50),
        'volatility_bbp': (0, 1),
        'volatility_atr': (0, 50),
        'volatility_ui': (0, 20),
        'trend_adx': (0, 100),
        'trend_cci': (-300, 300),
        'trend_macd': (-10, 10),
        'trend_macd_diff': (-5, 5),
        'trend_aroon_ind': (-100, 100),
        'volume_mfi': (0, 100),
        'volume_cmf': (-0.5, 0.5),
        'volume_fi': (-1000000, 1000000),
    }

    for item in indicator_filters:
        col = item.get('column')
        condition = item.get('condition')
        ref_col = item.get('reference_column')

        # Cross conditions are evaluated by the worker; we just need to
        # read the boolean column. Don't require the raw `column` to be
        # on the row (e.g. the cross column might be there but the raw
        # SMA column might not).
        if condition in ('crossed_above', 'crossed_below') and ref_col:
            global _CROSS_COLUMN_NAME
            if _CROSS_COLUMN_NAME is None:
                from app.services.agno_screener import _cross_column_name as _cn
                _CROSS_COLUMN_NAME = _cn
            cross_col = _CROSS_COLUMN_NAME(item)
            if cross_col in row.index:
                val = row[cross_col]
                if pd.isna(val):
                    continue
                bonuses.append(100.0 if bool(val) else 0.0)
                continue
            # Cross column not on the row — fall through to legacy
            # min/max logic below (which will likely append 0 if there's
            # no usable data on `col`).

        if not col or col not in row.index:
            continue
        actual = row[col]
        if pd.isna(actual):
            continue

        min_val = item.get('min')
        max_val = item.get('max')
        ref_min, ref_max = ref_ranges.get(col, (0, 100))

        if min_val is not None and actual >= min_val:
            # How far above the minimum? Scale to ref_max.
            if ref_max > min_val:
                bonus = 50 + min(50, (actual - min_val) / (ref_max - min_val) * 50)
            else:
                bonus = 50
            bonuses.append(bonus)
        elif max_val is not None and actual <= max_val:
            # How far below the maximum? Scale to ref_min.
            if max_val > ref_min:
                bonus = 50 + min(50, (max_val - actual) / (max_val - ref_min) * 50)
            else:
                bonus = 50
            bonuses.append(bonus)
        else:
            # Filter not satisfied
            bonuses.append(0)

    # Legacy filters
    if filters.get('rsi_min') is not None:
        rsi = row.get('momentum_rsi')
        if rsi is not None and rsi >= filters['rsi_min']:
            bonuses.append(50 + min(50, (rsi - filters['rsi_min']) / (100 - filters['rsi_min']) * 50))
        else:
            bonuses.append(0)

    if filters.get('rsi_max') is not None:
        rsi = row.get('momentum_rsi')
        if rsi is not None and rsi <= filters['rsi_max']:
            bonuses.append(50 + min(50, (filters['rsi_max'] - rsi) / (filters['rsi_max'] - 0) * 50))
        else:
            bonuses.append(0)

    if filters.get('volume_ratio_min') is not None:
        vr = row.get('volume_ratio')
        if vr is not None and vr >= filters['volume_ratio_min']:
            bonuses.append(50 + min(50, (vr - filters['volume_ratio_min']) / (5.0 - filters['volume_ratio_min']) * 50))
        else:
            bonuses.append(0)

    if filters.get('ath_proximity_min') is not None:
        ath = row.get('ath_proximity')
        if ath is not None and ath >= filters['ath_proximity_min']:
            bonuses.append(50 + min(50, (ath - filters['ath_proximity_min']) / (1.0 - filters['ath_proximity_min']) * 50))
        else:
            bonuses.append(0)

    if not bonuses:
        return 50.0  # Neutral bonus when no filters applied

    return round(sum(bonuses) / len(bonuses), 1)


def compute_quant_score(
    row: pd.Series,
    filters: Dict[str, Any],
    base_weight: int = 60,
    sub_weights: Optional[Dict[str, int]] = None,
    include_alignment: bool = False,
) -> Dict[str, Any]:
    """Compute the hybrid quant score and optional alignment diagnostic.

    Returns a dict with at least `score`. When `include_alignment` is True
    and the row carries a `return_pct`, also returns `score_minus_return`
    (score minus the return clipped to [-100, 100]).
    """
    base = compute_base_setup_score(row, sub_weights)
    bonus = compute_filter_match_bonus(row, filters)
    bw = max(0, min(100, base_weight)) / 100.0
    score = round(base * bw + bonus * (1 - bw), 1)
    out: Dict[str, Any] = {'score': score}
    if include_alignment and row.get('return_pct') is not None:
        normalized_return = max(-100.0, min(100.0, float(row['return_pct'])))
        out['score_minus_return'] = round(score - normalized_return, 1)
    return out


def compute_cross_angle(
    fast_series: pd.Series,
    slow_series: pd.Series,
    close_series: pd.Series,
    cross_index: int,
) -> float:
    """Compute crossover angle using backward differencing.

    gap(t) = fast(t) - slow(t)
    angle = (gap(cross_index) - gap(cross_index - 1)) / close(cross_index) * 100

    Returns percentage (e.g., 0.5 = 0.5% gap widening per bar).
    """
    if cross_index < 1 or cross_index >= len(fast_series):
        return 0.0
    gap_now = fast_series.iloc[cross_index] - slow_series.iloc[cross_index]
    gap_prev = fast_series.iloc[cross_index - 1] - slow_series.iloc[cross_index - 1]
    close_now = close_series.iloc[cross_index]
    if close_now == 0 or pd.isna(close_now):
        return 0.0
    return float((gap_now - gap_prev) / close_now * 100)


# =============================================================================
