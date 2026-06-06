"""
Scoring functions for Quant Strategy screening.
Extracted from agno_screener.py for better maintainability.
"""

import logging
from typing import Dict, Any

import pandas as pd

logger = logging.getLogger(__name__)

def compute_base_setup_breakdown(row: pd.Series) -> Dict[str, float]:
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
    rsi = row.get('momentum_rsi', 50)
    rsi_score = max(0, 100 - abs(rsi - 55) * 2.5)
    roc = row.get('momentum_roc', 0)
    roc_score = min(100, max(0, 50 + roc * 5)) if roc is not None else 50
    stoch = row.get('momentum_stoch', 50)
    stoch_score = max(0, 100 - abs(stoch - 50) * 2) if stoch is not None else 50
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

    total = round(
        trend_score * 0.30 +
        momentum_score * 0.25 +
        volatility_score * 0.20 +
        volume_score * 0.25, 1
    )

    return {
        'trend_score': trend_score,
        'momentum_score': momentum_score,
        'volatility_score': volatility_score,
        'volume_score': volume_score,
        'total': total,
    }


def compute_base_setup_score(row: pd.Series) -> float:
    """Compute a 0-100 base setup score from technical indicators."""
    return compute_base_setup_breakdown(row)['total']


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


def compute_quant_score(row: pd.Series, filters: Dict[str, Any], base_weight: int = 60) -> float:
    """Compute hybrid final score with adjustable base setup weight (0-100)."""
    base = compute_base_setup_score(row)
    bonus = compute_filter_match_bonus(row, filters)
    bw = max(0, min(100, base_weight)) / 100.0
    return round(base * bw + bonus * (1 - bw), 1)


# =============================================================================
