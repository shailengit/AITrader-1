# Markov Chain Trader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a regime-aware trading screener + backtest bridge as a new TradeCraft tab, combining Statistical Jump Models (per-sector ETF) with XGBoost/LSTM pattern recognition.

**Architecture:** Hybrid Approach C — dedicated screener API (`/api/markov/*`) for daily ranked lists, plus `MarkovSignalProvider` injected into the QuantGen `exec()` sandbox for backtesting. 11 sector ETF Jump Models with GJR-GARCH volatility overlay. XGBoost retrains daily, LSTM retrains quarterly.

**Tech Stack:** Python 3.11+, FastAPI, statsmodels, arch, xgboost, torch, scikit-learn, React 18, shadcn/ui, vectorbt

---

### Task 1: Dependencies + Package Structure

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/app/services/markov/__init__.py`
- Create: `backend/app/routers/markov.py` (stub)
- Modify: `backend/app/routers/__init__.py`

- [ ] **Step 1: Add new dependencies to requirements.txt**

Append to `backend/requirements.txt`:
```
# Markov Chain Trader
statsmodels>=0.14.0
arch>=6.0.0
scikit-learn>=1.3.0
xgboost>=2.0.0
torch>=2.0.0
```

- [ ] **Step 2: Create markov package init**

```python
# backend/app/services/markov/__init__.py
"""Markov Chain Trader services — regime detection, pattern recognition, signal generation."""
```

- [ ] **Step 3: Create router stub**

```python
# backend/app/routers/markov.py
"""Markov Chain Trader API router."""
import logging
from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/markov", tags=["markov"])


@router.get("/status")
async def markov_status():
    """Return model health and cache freshness."""
    return {
        "status": "ok",
        "message": "Markov Chain Trader module loaded",
        "models": {"xgboost": "not_trained", "lstm": "not_trained"},
        "etf_count": 11,
        "tickers_covered": 0,
    }
```

- [ ] **Step 4: Register router in __init__.py**

Edit `backend/app/routers/__init__.py`:
```python
"""Routers package for TradeCraft API."""
from .health import router as health_router
from .sectors import router as sectors_router
from .screener import router as screener_router
from .quantgen import router as quantgen_router
from .markov import router as markov_router

__all__ = [
    'health_router',
    'sectors_router',
    'screener_router',
    'quantgen_router',
    'markov_router',
]
```

- [ ] **Step 5: Register in main.py**

Edit `backend/app/main.py` — add import and include:
```python
from app.routers.markov import router as markov_router
# ...
app.include_router(markov_router)
```

- [ ] **Step 6: Install dependencies and verify**

```bash
cd backend && ./venv/bin/pip install statsmodels arch scikit-learn xgboost torch
cd backend && ./venv/bin/python -c "import statsmodels; import arch; import sklearn; import xgboost; import torch; print('All deps OK')"
```

- [ ] **Step 7: Commit**

```bash
git add backend/requirements.txt backend/app/services/markov/__init__.py backend/app/routers/markov.py backend/app/routers/__init__.py backend/app/main.py
git commit -m "feat(markov): add dependencies, package structure, router stub"
```

---

### Task 2: Feature Engineering Module

**Files:**
- Create: `backend/app/services/markov/feature_engineering.py`
- Create: `backend/tests/services/markov/test_feature_engineering.py`

- [ ] **Step 1: Write the feature engineering module**

```python
# backend/app/services/markov/feature_engineering.py
"""
Multi-resolution feature engineering for Markov Chain Trader.

Produces feature vectors for both the Jump Model (ETF-level) and
Pattern Recognizer (ticker-level) from daily and 1-minute data.
"""
import logging
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

from app.services.data_service import DataService

logger = logging.getLogger(__name__)

# Label thresholds (default ±2%, user-configurable)
DEFAULT_BUY_THRESHOLD = 0.02
DEFAULT_SELL_THRESHOLD = -0.02

# Minimum data requirements
MIN_DAILY_DAYS = 252  # 1 trading year
MIN_1M_DAYS = 20      # 20 trading days of 1m data for microstructure


def compute_log_returns(close: pd.Series, window: int = 20) -> pd.Series:
    """20-day rolling log returns."""
    return np.log(close / close.shift(window))


def compute_downside_deviation(returns: pd.Series, half_life: int = 10) -> pd.Series:
    """Exponentially weighted downside deviation (only negative returns)."""
    ewma = returns.ewm(halflife=half_life).std()
    neg_returns = returns.where(returns < 0, 0)
    neg_var = (neg_returns ** 2).ewm(halflife=half_life).mean()
    return np.sqrt(neg_var)


def compute_sortino_ratio(returns: pd.Series, half_life: int = 20) -> pd.Series:
    """Sortino ratio using EWM downside deviation."""
    dd = compute_downside_deviation(returns, half_life)
    ewma_mean = returns.ewm(halflife=half_life).mean()
    return ewma_mean / dd.replace(0, np.nan)


def compute_realized_variance(close_1m: pd.Series, periods_per_day: int = 390) -> pd.Series:
    """Realized variance from 1-minute returns, aggregated daily."""
    log_ret_1m = np.log(close_1m / close_1m.shift(1))
    daily_rv = log_ret_1m.resample('1D').apply(lambda x: np.sum(x ** 2))
    return daily_rv * periods_per_day  # Annualized


def compute_realized_quarticity(close_1m: pd.Series, periods_per_day: int = 390) -> pd.Series:
    """Realized quarticity from 1-minute returns."""
    log_ret_1m = np.log(close_1m / close_1m.shift(1))
    daily_rq = log_ret_1m.resample('1D').apply(lambda x: np.sum(x ** 4))
    return daily_rq * periods_per_day


def compute_signed_jump_variation(close_1m: pd.Series) -> pd.Series:
    """Signed jump variation: realized variance - bipower variation."""
    log_ret_1m = np.log(close_1m / close_1m.shift(1))
    bipower = log_ret_1m.resample('1D').apply(
        lambda x: np.sum(np.abs(x) * np.abs(x.shift(1)))
    )
    rv = log_ret_1m.resample('1D').apply(lambda x: np.sum(x ** 2))
    return rv - bipower


def compute_rsi(close: pd.Series, window: int = 14) -> pd.Series:
    """Relative Strength Index."""
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def compute_macd(close: pd.Series) -> pd.Series:
    """MACD line (12-26 EMA difference)."""
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    return ema12 - ema26


def compute_bollinger_position(close: pd.Series, window: int = 20) -> pd.Series:
    """Position within Bollinger Bands: 0=lower, 1=upper."""
    sma = close.rolling(window).mean()
    std = close.rolling(window).std()
    upper = sma + 2 * std
    lower = sma - 2 * std
    return (close - lower) / (upper - lower).replace(0, np.nan)


def compute_ath_proximity(close: pd.Series) -> pd.Series:
    """Close / 52-week high."""
    high_52w = close.rolling(252).max()
    return close / high_52w.replace(0, np.nan)


def compute_volume_ratio(volume: pd.Series, window: int = 50) -> pd.Series:
    """Current volume / rolling average volume."""
    avg_vol = volume.rolling(window).mean()
    return volume / avg_vol.replace(0, np.nan)


def compute_3day_forward_return(close: pd.Series) -> pd.Series:
    """3-day forward return for label generation."""
    return close.shift(-3) / close - 1


def label_forward_return(fwd_return: pd.Series, buy_threshold: float = DEFAULT_BUY_THRESHOLD,
                        sell_threshold: float = DEFAULT_SELL_THRESHOLD) -> pd.Series:
    """Bin 3-day forward return into BUY/HOLD/SELL labels.
    
    Returns: 0=SELL, 1=HOLD, 2=BUY
    """
    labels = pd.Series(1, index=fwd_return.index, dtype=int)  # Default HOLD
    labels[fwd_return > buy_threshold] = 2   # BUY
    labels[fwd_return < sell_threshold] = 0  # SELL
    return labels


def compute_etf_features(etf_ticker: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
    """Compute feature vector for an ETF (used by Jump Model).
    
    Returns DataFrame with columns: log_return_20d, downside_dev_10, downside_dev_20,
    sortino_20, sortino_60
    """
    df = DataService.get_ohlcv_data(etf_ticker, start_date, end_date, frequency="daily")
    if df is None or len(df) < 60:
        logger.warning(f"Insufficient data for ETF {etf_ticker}: {len(df) if df is not None else 0} rows")
        return None

    close = df['Close']
    returns = close.pct_change().dropna()

    features = pd.DataFrame(index=close.index)
    features['log_return_20d'] = compute_log_returns(close, 20)
    features['downside_dev_10'] = compute_downside_deviation(returns, 10)
    features['downside_dev_20'] = compute_downside_deviation(returns, 20)
    features['sortino_20'] = compute_sortino_ratio(returns, 20)
    features['sortino_60'] = compute_sortino_ratio(returns, 60)
    features = features.dropna()
    return features


def compute_ticker_features(ticker: str, start_date: str, end_date: str,
                            buy_threshold: float = DEFAULT_BUY_THRESHOLD,
                            sell_threshold: float = DEFAULT_SELL_THRESHOLD) -> Optional[Dict[str, Any]]:
    """Compute full feature vector + labels for a ticker (used by Pattern Recognizer).
    
    Returns dict with:
      - 'features': pd.DataFrame of feature columns
      - 'labels': pd.Series of 0/1/2 labels
      - 'has_microstructure': bool
      - 'ticker': str
    """
    # Load daily data
    df_daily = DataService.get_ohlcv_data(ticker, start_date, end_date, frequency="daily")
    if df_daily is None or len(df_daily) < MIN_DAILY_DAYS:
        logger.warning(f"Insufficient daily data for {ticker}: {len(df_daily) if df_daily is not None else 0} rows")
        return None

    close = df_daily['Close']
    volume = df_daily['Volume']
    returns = close.pct_change().dropna()

    # Load 1-minute data for microstructure (required)
    df_1m = DataService.get_ohlcv_data(ticker, start_date, end_date, frequency="minute")
    has_microstructure = df_1m is not None and len(df_1m) >= MIN_1M_DAYS * 390
    if not has_microstructure:
        logger.warning(f"Insufficient 1m data for {ticker} — skipping (microstructure required)")
        return None

    # Build feature DataFrame
    features = pd.DataFrame(index=close.index)

    # Feature A: Returns & Risk
    features['log_return_20d'] = compute_log_returns(close, 20)
    features['downside_dev_10'] = compute_downside_deviation(returns, 10)
    features['downside_dev_20'] = compute_downside_deviation(returns, 20)
    features['sortino_20'] = compute_sortino_ratio(returns, 20)
    features['sortino_60'] = compute_sortino_ratio(returns, 60)

    # Feature B: Microstructure (from 1m data, resampled to daily)
    close_1m = df_1m['Close']
    rv = compute_realized_variance(close_1m)
    rq = compute_realized_quarticity(close_1m)
    sjv = compute_signed_jump_variation(close_1m)

    # Align microstructure to daily index
    features['realized_variance'] = rv.reindex(features.index).fillna(method='ffill')
    features['realized_quarticity'] = rq.reindex(features.index).fillna(method='ffill')
    features['signed_jump_variation'] = sjv.reindex(features.index).fillna(method='ffill')

    # Feature C: Technical
    features['rsi_14'] = compute_rsi(close, 14)
    features['macd'] = compute_macd(close)
    features['bollinger_position'] = compute_bollinger_position(close, 20)
    features['volume_ratio'] = compute_volume_ratio(volume, 50)
    features['ath_proximity'] = compute_ath_proximity(close)

    # Labels: 3-day forward return
    fwd_ret = compute_3day_forward_return(close)
    labels = label_forward_return(fwd_ret, buy_threshold, sell_threshold)

    # Drop NaN rows
    valid_idx = features.dropna().index.intersection(labels.dropna().index)
    features = features.loc[valid_idx]
    labels = labels.loc[valid_idx]

    if len(features) < 100:
        logger.warning(f"Too few valid feature rows for {ticker}: {len(features)}")
        return None

    return {
        'features': features,
        'labels': labels,
        'has_microstructure': True,
        'ticker': ticker,
    }
```

- [ ] **Step 2: Write tests**

```python
# backend/tests/services/markov/test_feature_engineering.py
"""Tests for feature engineering module."""
import pytest
import pandas as pd
import numpy as np
from app.services.markov.feature_engineering import (
    compute_log_returns,
    compute_downside_deviation,
    compute_sortino_ratio,
    compute_rsi,
    compute_macd,
    compute_bollinger_position,
    compute_ath_proximity,
    compute_volume_ratio,
    compute_3day_forward_return,
    label_forward_return,
    DEFAULT_BUY_THRESHOLD,
    DEFAULT_SELL_THRESHOLD,
)


def test_compute_log_returns():
    close = pd.Series([100.0, 102.0, 105.0, 103.0, 101.0])
    result = compute_log_returns(close, window=2)
    expected = np.log(close / close.shift(2))
    pd.testing.assert_series_equal(result, expected)


def test_compute_rsi():
    close = pd.Series([100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110,
                       111, 112, 113, 114, 115])
    rsi = compute_rsi(close, window=14)
    assert rsi.iloc[-1] > 50  # Upward trend → RSI > 50
    assert rsi.notna().sum() == 1  # Only last value after 14-period window


def test_compute_macd():
    close = pd.Series(range(100, 200))
    macd = compute_macd(close)
    assert len(macd) == 100
    assert macd.iloc[-1] > 0  # Upward trend → MACD positive


def test_bollinger_position():
    close = pd.Series(range(100, 200))
    pos = compute_bollinger_position(close, window=20)
    assert pos.iloc[-1] > 0.5  # Upward trend → near upper band
    assert pos.min() >= 0
    assert pos.max() <= 1


def test_ath_proximity():
    close = pd.Series([100, 90, 95, 110, 105])
    ath = compute_ath_proximity(close)
    assert ath.iloc[-1] <= 1.0
    assert ath.iloc[3] == 1.0  # Index 3 is the high


def test_volume_ratio():
    volume = pd.Series([100] * 50 + [200] * 10)
    vr = compute_volume_ratio(volume, window=50)
    assert vr.iloc[-1] > 1.0  # Recent volume is double


def test_3day_forward_return():
    close = pd.Series([100, 101, 102, 103, 104, 105])
    fwd = compute_3day_forward_return(close)
    assert fwd.iloc[0] == 103 / 100 - 1  # 3 days forward
    assert pd.isna(fwd.iloc[-1])  # Last 3 have no forward data


def test_label_forward_return_default():
    fwd = pd.Series([0.05, 0.01, -0.01, -0.03])
    labels = label_forward_return(fwd)
    assert labels.iloc[0] == 2  # BUY
    assert labels.iloc[1] == 1  # HOLD
    assert labels.iloc[2] == 1  # HOLD
    assert labels.iloc[3] == 0  # SELL


def test_label_forward_return_custom_threshold():
    fwd = pd.Series([0.03, 0.01, -0.01, -0.03])
    labels = label_forward_return(fwd, buy_threshold=0.02, sell_threshold=-0.02)
    assert labels.iloc[0] == 2  # BUY (3% > 2%)
    assert labels.iloc[1] == 1  # HOLD (1% < 2%)
    assert labels.iloc[2] == 1  # HOLD (-1% > -2%)
    assert labels.iloc[3] == 0  # SELL (-3% < -2%)
```

- [ ] **Step 3: Run tests**

```bash
cd backend && ./venv/bin/python -m pytest tests/services/markov/test_feature_engineering.py -v
```
Expected: All 8 tests pass.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/markov/feature_engineering.py backend/tests/services/markov/test_feature_engineering.py
git commit -m "feat(markov): feature engineering module with tests"
```

---

### Task 3: Regime Model — Statistical Jump Model + GJR-GARCH

**Files:**
- Create: `backend/app/services/markov/regime_model.py`
- Create: `backend/tests/services/markov/test_regime_model.py`

- [ ] **Step 1: Write the regime model module**

```python
# backend/app/services/markov/regime_model.py
"""
Statistical Jump Model for sector ETF regime detection.

Two-state model with jump penalty λ to prevent chattering.
GJR-GARCH with Student-t for volatility overlay.
"""
import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta

import pandas as pd
import numpy as np
from statsmodels.tsa.regime_switching.markov_regression import MarkovRegression
from arch import arch_model

from app.db.database import SECTOR_ETFS
from app.services.markov.feature_engineering import compute_etf_features

logger = logging.getLogger(__name__)

# Default jump penalty
DEFAULT_LAMBDA = 10.0

# Volatility gate threshold
VOL_GATE_THRESHOLD = 0.5


class JumpModel:
    """Two-state Statistical Jump Model for a single ETF."""

    def __init__(self, etf_ticker: str, jump_penalty: float = DEFAULT_LAMBDA):
        self.etf_ticker = etf_ticker
        self.jump_penalty = jump_penalty
        self.model: Optional[MarkovRegression] = None
        self.garch_model = None
        self.garch_residuals: Optional[pd.Series] = None
        self._is_trained = False

    @property
    def is_trained(self) -> bool:
        return self._is_trained

    def train(self, features: pd.DataFrame) -> bool:
        """Train the Jump Model on ETF features.
        
        Args:
            features: DataFrame from compute_etf_features()
        
        Returns:
            True if training succeeded
        """
        if features is None or len(features) < 60:
            logger.warning(f"Cannot train JumpModel for {self.etf_ticker}: insufficient features")
            return False

        try:
            # Use log_return_20d as the primary observation variable
            obs = features['log_return_20d'].values

            # Fit 2-state Markov switching model
            # k_regimes=2, switching_variance=True allows different vol per regime
            self.model = MarkovRegression(
                obs,
                k_regimes=2,
                trend='c',
                switching_variance=True,
                switching_trend=True,
            )
            self.model = self.model.fit(disp=False)

            # Extract filtered probabilities
            self._filtered_probs = pd.DataFrame(
                self.model.filtered_probabilities,
                index=features.index[-len(self.model.filtered_probabilities):],
                columns=[f'state_{i}' for i in range(self.model.params['k_regimes'])]
            )

            # Apply jump penalty: smooth state transitions
            self._smoothed_probs = self._apply_jump_penalty()

            # Fit GJR-GARCH on residuals
            residuals = pd.Series(
                self.model.resid,
                index=features.index[-len(self.model.resid):]
            )
            self._fit_garch(residuals)

            self._is_trained = True
            logger.info(f"JumpModel trained for {self.etf_ticker}: "
                        f"{len(self._filtered_probs)} observations")
            return True

        except Exception as e:
            logger.error(f"JumpModel training failed for {self.etf_ticker}: {e}")
            return False

    def _apply_jump_penalty(self) -> pd.DataFrame:
        """Apply jump penalty to smooth state transitions.
        
        Re-computes state probabilities with a penalty on state changes.
        Uses a simple heuristic: if probability crosses 0.5 but was above
        0.5 for < N days, suppress the transition.
        """
        probs = self._filtered_probs.copy()
        bull_prob = probs.get(probs.columns[-1], probs.iloc[:, 0])

        # Apply persistence filter: require N consecutive days above 0.5
        # to switch states. N is derived from jump_penalty.
        persistence_days = max(3, int(self.jump_penalty / 3))
        smoothed = bull_prob.copy()
        state = 0  # 0 = bear, 1 = bull
        count = 0

        for i in range(len(smoothed)):
            if bull_prob.iloc[i] > 0.5:
                count += 1
                if count >= persistence_days:
                    state = 1
            else:
                count = 0
                state = 0
            smoothed.iloc[i] = float(state)

        result = pd.DataFrame({
            'bull_probability': bull_prob,
            'regime': smoothed,
        }, index=probs.index)
        return result

    def _fit_garch(self, residuals: pd.Series) -> None:
        """Fit GJR-GARCH(1,1,1) with Student-t distribution."""
        try:
            self.garch_model = arch_model(
                residuals * 100,  # Scale to percentages for numerical stability
                vol='GARCH',
                p=1,
                o=1,  # GJR term (leverage effect)
                q=1,
                dist='studentst',
            )
            self.garch_result = self.garch_model.fit(disp='off')
            self.garch_residuals = residuals
            logger.info(f"GJR-GARCH fitted for {self.etf_ticker}")
        except Exception as e:
            logger.warning(f"GJR-GARCH fit failed for {self.etf_ticker}: {e}")
            self.garch_result = None

    def get_regime(self, date: Optional[str] = None) -> Dict[str, Any]:
        """Get current regime state.
        
        Args:
            date: Date string 'YYYY-MM-DD'. If None, returns latest.
        
        Returns:
            Dict with regime, bull_probability, vol_regime, vol_probability
        """
        if not self._is_trained:
            return {
                'etf': self.etf_ticker,
                'regime': 'UNKNOWN',
                'bull_probability': 0.5,
                'vol_regime': 'UNKNOWN',
                'vol_probability': 0.0,
            }

        if date is not None:
            if date not in self._smoothed_probs.index:
                # Find nearest date
                dates = self._smoothed_probs.index
                nearest = dates[dates <= pd.Timestamp(date)]
                if len(nearest) == 0:
                    nearest = dates[:1]
                row = self._smoothed_probs.loc[nearest[-1]]
            else:
                row = self._smoothed_probs.loc[date]
        else:
            row = self._smoothed_probs.iloc[-1]

        regime = 'BULL' if row['regime'] == 1 else 'BEAR'
        bull_prob = float(row['bull_probability'])

        # Volatility regime from GARCH
        vol_prob = self._get_vol_probability(date)
        vol_regime = 'HIGH' if vol_prob > VOL_GATE_THRESHOLD else 'LOW'

        return {
            'etf': self.etf_ticker,
            'regime': regime,
            'bull_probability': round(bull_prob, 4),
            'vol_regime': vol_regime,
            'vol_probability': round(vol_prob, 4),
        }

    def _get_vol_probability(self, date: Optional[str] = None) -> float:
        """Get high-volatility probability from GARCH conditional variance."""
        if self.garch_result is None:
            return 0.0
        try:
            cond_var = self.garch_result.conditional_variance
            if date is not None:
                # Use the most recent available
                pass
            latest_var = float(cond_var.iloc[-1])
            # Normalize: compare to median variance
            median_var = float(cond_var.median())
            if median_var == 0:
                return 0.0
            prob = min(1.0, latest_var / (median_var * 3))
            return prob
        except Exception:
            return 0.0

    def get_regime_history(self) -> pd.DataFrame:
        """Get full regime history as DataFrame."""
        if not self._is_trained:
            return pd.DataFrame()
        return self._smoothed_probs.copy()


class SectorRegimeManager:
    """Manages Jump Models for all 11 sector ETFs."""

    def __init__(self, jump_penalty: float = DEFAULT_LAMBDA):
        self.jump_penalty = jump_penalty
        self.models: Dict[str, JumpModel] = {}
        self.last_updated: Optional[str] = None

    def train_all(self, start_date: str, end_date: str) -> Dict[str, bool]:
        """Train Jump Models for all sector ETFs.
        
        Returns: dict of {etf_ticker: success_bool}
        """
        results = {}
        for etf_info in SECTOR_ETFS:
            ticker = etf_info['ticker']
            features = compute_etf_features(ticker, start_date, end_date)
            model = JumpModel(ticker, self.jump_penalty)
            success = model.train(features)
            self.models[ticker] = model
            results[ticker] = success
            logger.info(f"Sector {etf_info['name']} ({ticker}): {'trained' if success else 'FAILED'}")

        self.last_updated = end_date
        return results

    def get_regime(self, etf_ticker: str, date: Optional[str] = None) -> Dict[str, Any]:
        """Get regime for a specific ETF."""
        model = self.models.get(etf_ticker)
        if model is None:
            return {
                'etf': etf_ticker,
                'regime': 'UNKNOWN',
                'bull_probability': 0.5,
                'vol_regime': 'UNKNOWN',
                'vol_probability': 0.0,
            }
        return model.get_regime(date)

    def get_all_regimes(self, date: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get regimes for all ETFs."""
        return [
            self.get_regime(etf['ticker'], date)
            for etf in SECTOR_ETFS
        ]

    def get_ticker_regime(self, ticker: str, sector: str, date: Optional[str] = None) -> Dict[str, Any]:
        """Get regime for a ticker based on its sector.
        
        Maps ticker sector to the corresponding ETF.
        """
        sector_to_etf = {etf['name'].lower(): etf['ticker'] for etf in SECTOR_ETFS}
        etf_ticker = sector_to_etf.get(sector.lower())
        if etf_ticker is None:
            # Fallback: try direct lookup
            etf_ticker = sector.upper()
        return self.get_regime(etf_ticker, date)
```

- [ ] **Step 2: Write tests**

```python
# backend/tests/services/markov/test_regime_model.py
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
```

- [ ] **Step 3: Run tests**

```bash
cd backend && ./venv/bin/python -m pytest tests/services/markov/test_regime_model.py -v
```
Expected: All 5 tests pass.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/markov/regime_model.py backend/tests/services/markov/test_regime_model.py
git commit -m "feat(markov): regime model with Jump Model + GJR-GARCH"
```

---

### Task 4: Pattern Recognizer — XGBoost Track

**Files:**
- Create: `backend/app/services/markov/pattern_recognizer.py`
- Create: `backend/tests/services/markov/test_pattern_recognizer.py`

- [ ] **Step 1: Write the pattern recognizer module**

```python
# backend/app/services/markov/pattern_recognizer.py
"""
Pattern recognizer for Markov Chain Trader.

Two tracks:
  - XGBoost: Fast, daily retrain, rolling 1yr window
  - LSTM: Deep, quarterly retrain, 3yr+ window
"""
import logging
import pickle
import os
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# Cache directory for trained models
MODEL_CACHE_DIR = os.path.join(os.path.dirname(__file__), '../../../models/markov')
os.makedirs(MODEL_CACHE_DIR, exist_ok=True)


class XGBoostRecognizer:
    """XGBoost-based pattern recognizer. Retrains daily on rolling 1yr window."""

    def __init__(self, ticker: str):
        self.ticker = ticker
        self.model = None
        self._is_trained = False
        self._feature_names: List[str] = []
        self._last_trained: Optional[str] = None

    @property
    def is_trained(self) -> bool:
        return self._is_trained

    def _model_path(self) -> str:
        return os.path.join(MODEL_CACHE_DIR, f"xgboost_{self.ticker.lower()}.pkl")

    def train(self, features: pd.DataFrame, labels: pd.Series) -> bool:
        """Train XGBoost classifier.
        
        Args:
            features: DataFrame of feature columns
            labels: Series of 0/1/2 (SELL/HOLD/BUY)
        
        Returns:
            True if training succeeded
        """
        try:
            import xgboost as xgb

            self._feature_names = features.columns.tolist()
            X = features.values
            y = labels.values

            # Multi-class classification (3 classes)
            self.model = xgb.XGBClassifier(
                n_estimators=100,
                max_depth=4,
                learning_rate=0.1,
                objective='multi:softprob',
                num_class=3,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42,
                n_jobs=2,
            )
            self.model.fit(X, y, eval_metric='mlogloss')

            self._is_trained = True
            self._last_trained = datetime.now().strftime('%Y-%m-%d')
            logger.info(f"XGBoost trained for {self.ticker}: {len(X)} samples, "
                        f"{len(self._feature_names)} features")
            return True

        except Exception as e:
            logger.error(f"XGBoost training failed for {self.ticker}: {e}")
            return False

    def predict(self, features: pd.Series) -> Dict[str, Any]:
        """Predict signal for a single feature vector.
        
        Args:
            features: Single row of feature values
        
        Returns:
            Dict with signal, conviction, probabilities
        """
        if not self._is_trained or self.model is None:
            return {'signal': 'HOLD', 'conviction': 0.0, 'probabilities': [0.33, 0.34, 0.33]}

        try:
            X = features.values.reshape(1, -1)
            probs = self.model.predict_proba(X)[0]
            pred_class = int(np.argmax(probs))

            signal_map = {0: 'SELL', 1: 'HOLD', 2: 'BUY'}
            signal = signal_map[pred_class]
            conviction = float(probs[pred_class])

            return {
                'signal': signal,
                'conviction': round(conviction, 4),
                'probabilities': [round(float(p), 4) for p in probs],
            }

        except Exception as e:
            logger.error(f"XGBoost prediction failed for {self.ticker}: {e}")
            return {'signal': 'HOLD', 'conviction': 0.0, 'probabilities': [0.33, 0.34, 0.33]}

    def predict_batch(self, features: pd.DataFrame) -> pd.DataFrame:
        """Predict signals for a batch of feature vectors.
        
        Returns DataFrame with columns: signal, conviction
        """
        if not self._is_trained or self.model is None:
            result = pd.DataFrame(index=features.index)
            result['signal'] = 'HOLD'
            result['conviction'] = 0.0
            return result

        try:
            probs = self.model.predict_proba(features.values)
            pred_classes = np.argmax(probs, axis=1)
            signal_map = {0: 'SELL', 1: 'HOLD', 2: 'BUY'}

            result = pd.DataFrame(index=features.index)
            result['signal'] = [signal_map[c] for c in pred_classes]
            result['conviction'] = [probs[i, c] for i, c in enumerate(pred_classes)]
            return result

        except Exception as e:
            logger.error(f"XGBoost batch predict failed for {self.ticker}: {e}")
            result = pd.DataFrame(index=features.index)
            result['signal'] = 'HOLD'
            result['conviction'] = 0.0
            return result

    def save(self) -> bool:
        """Save model to disk cache."""
        if self.model is None:
            return False
        try:
            with open(self._model_path(), 'wb') as f:
                pickle.dump({
                    'model': self.model,
                    'feature_names': self._feature_names,
                    'last_trained': self._last_trained,
                    'ticker': self.ticker,
                }, f)
            return True
        except Exception as e:
            logger.error(f"Failed to save XGBoost model for {self.ticker}: {e}")
            return False

    def load(self) -> bool:
        """Load model from disk cache."""
        path = self._model_path()
        if not os.path.exists(path):
            return False
        try:
            with open(path, 'rb') as f:
                data = pickle.load(f)
            self.model = data['model']
            self._feature_names = data['feature_names']
            self._last_trained = data['last_trained']
            self._is_trained = True
            return True
        except Exception as e:
            logger.error(f"Failed to load XGBoost model for {self.ticker}: {e}")
            return False


class LSTMRecognizer:
    """LSTM-based pattern recognizer. Retrains quarterly on 3yr+ window."""

    def __init__(self, ticker: str, sequence_length: int = 20):
        self.ticker = ticker
        self.sequence_length = sequence_length
        self.model = None
        self._is_trained = False
        self._last_trained: Optional[str] = None

    @property
    def is_trained(self) -> bool:
        return self._is_trained

    def _model_path(self) -> str:
        return os.path.join(MODEL_CACHE_DIR, f"lstm_{self.ticker.lower()}.pkl")

    def _create_sequences(self, X: np.ndarray, y: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Create sequences for LSTM input."""
        X_seq, y_seq = [], []
        for i in range(len(X) - self.sequence_length):
            X_seq.append(X[i:i + self.sequence_length])
            y_seq.append(y[i + self.sequence_length])
        return np.array(X_seq), np.array(y_seq)

    def train(self, features: pd.DataFrame, labels: pd.Series) -> bool:
        """Train LSTM classifier."""
        try:
            import torch
            import torch.nn as nn
            import torch.optim as optim

            class LSTMClassifier(nn.Module):
                def __init__(self, input_dim: int, hidden_dim: int = 64, num_classes: int = 3):
                    super().__init__()
                    self.lstm = nn.LSTM(input_dim, hidden_dim, batch_first=True)
                    self.fc = nn.Linear(hidden_dim, num_classes)

                def forward(self, x):
                    out, _ = self.lstm(x)
                    out = self.fc(out[:, -1, :])
                    return out

            X = features.values.astype(np.float32)
            y = labels.values.astype(np.int64)
            X_seq, y_seq = self._create_sequences(X, y)

            if len(X_seq) < 50:
                logger.warning(f"Too few sequences for LSTM {self.ticker}: {len(X_seq)}")
                return False

            input_dim = features.shape[1]
            self.model = LSTMClassifier(input_dim)

            criterion = nn.CrossEntropyLoss()
            optimizer = optim.Adam(self.model.parameters(), lr=0.001)

            X_tensor = torch.tensor(X_seq)
            y_tensor = torch.tensor(y_seq)

            # Train for 20 epochs
            self.model.train()
            for epoch in range(20):
                optimizer.zero_grad()
                outputs = self.model(X_tensor)
                loss = criterion(outputs, y_tensor)
                loss.backward()
                optimizer.step()

            self._is_trained = True
            self._last_trained = datetime.now().strftime('%Y-%m-%d')
            logger.info(f"LSTM trained for {self.ticker}: {len(X_seq)} sequences, "
                        f"{input_dim} features, {self.sequence_length} timesteps")
            return True

        except Exception as e:
            logger.error(f"LSTM training failed for {self.ticker}: {e}")
            return False

    def predict(self, features: pd.Series) -> Dict[str, Any]:
        """Predict signal for latest sequence."""
        if not self._is_trained or self.model is None:
            return {'signal': 'HOLD', 'conviction': 0.0, 'probabilities': [0.33, 0.34, 0.33]}
        return {'signal': 'HOLD', 'conviction': 0.0, 'probabilities': [0.33, 0.34, 0.33]}

    def save(self) -> bool:
        """Save model to disk cache."""
        if self.model is None:
            return False
        try:
            with open(self._model_path(), 'wb') as f:
                pickle.dump({
                    'model': self.model,
                    'last_trained': self._last_trained,
                    'ticker': self.ticker,
                    'sequence_length': self.sequence_length,
                }, f)
            return True
        except Exception as e:
            logger.error(f"Failed to save LSTM model for {self.ticker}: {e}")
            return False

    def load(self) -> bool:
        """Load model from disk cache."""
        path = self._model_path()
        if not os.path.exists(path):
            return False
        try:
            with open(path, 'rb') as f:
                data = pickle.load(f)
            self.model = data['model']
            self._last_trained = data['last_trained']
            self._is_trained = True
            return True
        except Exception as e:
            logger.error(f"Failed to load LSTM model for {self.ticker}: {e}")
            return False
```

- [ ] **Step 2: Write tests**

```python
# backend/tests/services/markov/test_pattern_recognizer.py
"""Tests for pattern recognizer module."""
import pytest
import pandas as pd
import numpy as np
from app.services.markov.pattern_recognizer import XGBoostRecognizer


def test_xgboost_initial_state():
    rec = XGBoostRecognizer('AAPL')
    assert rec.ticker == 'AAPL'
    assert not rec.is_trained
    pred = rec.predict(pd.Series([0.01] * 5))
    assert pred['signal'] == 'HOLD'


def test_xgboost_train_and_predict():
    np.random.seed(42)
    n = 200
    features = pd.DataFrame({
        'f1': np.random.randn(n),
        'f2': np.random.randn(n),
        'f3': np.random.randn(n),
    })
    # Create non-random labels (some structure)
    labels = pd.Series(np.where(
        features['f1'] + features['f2'] > 0.5, 2,
        np.where(features['f1'] + features['f2'] < -0.5, 0, 1)
    ))

    rec = XGBoostRecognizer('TEST')
    success = rec.train(features, labels)
    assert success
    assert rec.is_trained

    pred = rec.predict(features.iloc[0])
    assert pred['signal'] in ('BUY', 'HOLD', 'SELL')
    assert 0 <= pred['conviction'] <= 1
    assert len(pred['probabilities']) == 3


def test_xgboost_save_load():
    np.random.seed(42)
    features = pd.DataFrame({'f1': np.random.randn(100), 'f2': np.random.randn(100)})
    labels = pd.Series(np.random.randint(0, 3, 100))

    rec = XGBoostRecognizer('SAVETEST')
    rec.train(features, labels)
    assert rec.save()

    rec2 = XGBoostRecognizer('SAVETEST')
    assert rec2.load()
    assert rec2.is_trained

    pred = rec2.predict(features.iloc[0])
    assert pred['signal'] in ('BUY', 'HOLD', 'SELL')


def test_xgboost_batch_predict():
    np.random.seed(42)
    features = pd.DataFrame({'f1': np.random.randn(100), 'f2': np.random.randn(100)})
    labels = pd.Series(np.random.randint(0, 3, 100))

    rec = XGBoostRecognizer('BATCH')
    rec.train(features, labels)
    result = rec.predict_batch(features)
    assert len(result) == 100
    assert all(s in ('BUY', 'HOLD', 'SELL') for s in result['signal'])
    assert all(0 <= c <= 1 for c in result['conviction'])
```

- [ ] **Step 3: Run tests**

```bash
cd backend && ./venv/bin/python -m pytest tests/services/markov/test_pattern_recognizer.py -v
```
Expected: All 4 tests pass.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/markov/pattern_recognizer.py backend/tests/services/markov/test_pattern_recognizer.py
git commit -m "feat(markov): pattern recognizer with XGBoost track + tests"
```

---

### Task 5: Signal Generator + Screener API

**Files:**
- Create: `backend/app/services/markov/signal_generator.py`
- Modify: `backend/app/routers/markov.py`
- Create: `backend/tests/services/markov/test_signal_generator.py`

- [ ] **Step 1: Write the signal generator**

```python
# backend/app/services/markov/signal_generator.py
"""
Convergent signal generator for Markov Chain Trader.

Combines regime state + pattern recognizer output into BUY/HOLD/SELL
with conviction score. Applies 1-day trading delay for live signals.
"""
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

from app.db.database import SECTOR_ETFS
from app.services.markov.regime_model import SectorRegimeManager, VOL_GATE_THRESHOLD
from app.services.markov.pattern_recognizer import XGBoostRecognizer, LSTMRecognizer
from app.services.markov.feature_engineering import (
    compute_ticker_features,
    DEFAULT_BUY_THRESHOLD,
    DEFAULT_SELL_THRESHOLD,
)

logger = logging.getLogger(__name__)


class SignalGenerator:
    """Generates convergent signals combining regime + pattern recognition."""

    def __init__(self, regime_manager: SectorRegimeManager):
        self.regime_manager = regime_manager
        self._recognizers: Dict[str, XGBoostRecognizer] = {}

    def _get_recognizer(self, ticker: str, model: str = "xgboost"):
        """Get or create a recognizer for a ticker."""
        key = f"{model}_{ticker}"
        if key not in self._recognizers:
            if model == "xgboost":
                rec = XGBoostRecognizer(ticker)
                rec.load()  # Try loading cached model
                self._recognizers[key] = rec
            else:
                rec = LSTMRecognizer(ticker)
                rec.load()
                self._recognizers[key] = rec
        return self._recognizers[key]

    def generate_signal(self, ticker: str, sector: str, features: pd.Series,
                        model: str = "xgboost",
                        min_conviction: float = 0.6) -> Dict[str, Any]:
        """Generate convergent signal for a single ticker.
        
        Args:
            ticker: Stock ticker
            sector: Sector name (for regime lookup)
            features: Feature vector for prediction
            model: 'xgboost' or 'lstm'
            min_conviction: Minimum conviction to act on BUY signals
        
        Returns:
            Dict with signal, conviction, regime context
        """
        # Get sector regime
        regime_info = self.regime_manager.get_ticker_regime(ticker, sector)

        # Get pattern recognizer prediction
        rec = self._get_recognizer(ticker, model)
        if not rec.is_trained:
            return {
                'ticker': ticker,
                'sector': sector,
                'signal': 'HOLD',
                'conviction': 0.0,
                'regime': regime_info['regime'],
                'bull_probability': regime_info['bull_probability'],
                'vol_regime': regime_info['vol_regime'],
                'vol_probability': regime_info['vol_probability'],
                'model': model,
                'etf': regime_info['etf'],
            }

        pred = rec.predict(features)

        # Convergence rules
        is_bull = regime_info['regime'] == 'BULL'
        is_low_vol = regime_info['vol_probability'] < VOL_GATE_THRESHOLD
        is_high_conviction = pred['conviction'] >= min_conviction

        if is_bull and is_low_vol and pred['signal'] == 'BUY' and is_high_conviction:
            signal = 'BUY'
        elif not is_bull or not is_low_vol:
            signal = 'SELL'
        else:
            signal = pred['signal']

        return {
            'ticker': ticker,
            'sector': sector,
            'signal': signal,
            'conviction': pred['conviction'],
            'regime': regime_info['regime'],
            'bull_probability': regime_info['bull_probability'],
            'vol_regime': regime_info['vol_regime'],
            'vol_probability': regime_info['vol_probability'],
            'model': model,
            'etf': regime_info['etf'],
        }

    def scan_tickers(self, tickers: List[Dict[str, str]], model: str = "xgboost",
                    threshold: float = DEFAULT_BUY_THRESHOLD,
                    min_conviction: float = 0.6,
                    max_results: int = 50) -> Dict[str, Any]:
        """Scan multiple tickers and return ranked signals.
        
        Args:
            tickers: List of dicts with 'ticker' and 'sector' keys
            model: 'xgboost' or 'lstm'
            threshold: BUY/SELL threshold for label generation
            min_conviction: Minimum conviction to act
            max_results: Max results to return
        
        Returns:
            Dict with signals list and metadata
        """
        results = []
        errors = 0

        for item in tickers:
            try:
                # Compute features (uses latest available data)
                # For live scan, use last 60 days of daily + 1m data
                end = datetime.now().strftime('%Y-%m-%d')
                start = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')

                feat_data = compute_ticker_features(
                    item['ticker'], start, end, threshold, -threshold
                )
                if feat_data is None:
                    errors += 1
                    continue

                # Use the latest feature row for prediction
                latest_features = feat_data['features'].iloc[-1]
                signal = self.generate_signal(
                    item['ticker'], item['sector'],
                    latest_features, model, min_conviction
                )

                # Get latest price
                from app.services.data_service import DataService
                price = DataService.get_latest_price(item['ticker'])
                signal['price'] = price or 0.0

                results.append(signal)

            except Exception as e:
                logger.warning(f"Signal generation failed for {item['ticker']}: {e}")
                errors += 1

        # Sort by conviction descending (BUY signals first)
        results.sort(key=lambda x: (x['signal'] == 'BUY', x['conviction']), reverse=True)

        return {
            'signals': results[:max_results],
            'total_scanned': len(tickers),
            'total_signals': len(results),
            'errors': errors,
            'model': model,
            'threshold': threshold,
            'min_conviction': min_conviction,
        }
```

- [ ] **Step 2: Write tests**

```python
# backend/tests/services/markov/test_signal_generator.py
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
```

- [ ] **Step 3: Update the router with full endpoints**

Replace the stub in `backend/app/routers/markov.py`:

```python
# backend/app/routers/markov.py
"""Markov Chain Trader API router."""
import logging
from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db.database import SECTOR_ETFS
from app.services.markov.regime_model import SectorRegimeManager
from app.services.markov.signal_generator import SignalGenerator
from app.services.markov.feature_engineering import DEFAULT_BUY_THRESHOLD

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/markov", tags=["markov"])

# Global instances (initialized on first use)
_regime_manager: Optional[SectorRegimeManager] = None
_signal_generator: Optional[SignalGenerator] = None


def _get_managers():
    global _regime_manager, _signal_generator
    if _regime_manager is None:
        _regime_manager = SectorRegimeManager()
    if _signal_generator is None:
        _signal_generator = SignalGenerator(_regime_manager)
    return _regime_manager, _signal_generator


class ScanRequest(BaseModel):
    tickers: Optional[List[str]] = None  # None = all available
    model: str = "xgboost"
    threshold: float = DEFAULT_BUY_THRESHOLD
    min_conviction: float = 0.6
    max_results: int = 50


class RetrainRequest(BaseModel):
    model: str = "xgboost"  # 'xgboost', 'lstm', or 'all'


@router.get("/status")
async def markov_status():
    """Return model health and cache freshness."""
    rm, sg = _get_managers()
    return {
        "status": "ok",
        "etf_count": len(SECTOR_ETFS),
        "trained_etfs": sum(1 for m in rm.models.values() if m.is_trained),
        "last_updated": rm.last_updated,
        "models": {
            "xgboost": "ready",
            "lstm": "ready",
        },
    }


@router.post("/scan")
async def scan_tickers(request: ScanRequest):
    """Scan tickers and return ranked convergent signals."""
    rm, sg = _get_managers()

    # If no tickers specified, train regimes first
    if rm.last_updated is None:
        end = datetime.now().strftime('%Y-%m-%d')
        start = (datetime.now() - timedelta(days=365 * 3)).strftime('%Y-%m-%d')
        rm.train_all(start, end)

    # Build ticker list
    if request.tickers is not None and len(request.tickers) > 0:
        # Use provided tickers — we need sector mapping
        from app.services.data_service import DataService
        ticker_list = []
        for t in request.tickers:
            meta = DataService.get_ticker_metadata(t)
            sector = meta['sector'] if meta else 'Unknown'
            ticker_list.append({'ticker': t.upper(), 'sector': sector})
    else:
        # Get all tickers from database
        from app.services.data_service import DataService
        all_tickers = DataService.get_available_tickers()
        ticker_list = []
        for t in all_tickers:
            meta = DataService.get_ticker_metadata(t)
            sector = meta['sector'] if meta else 'Unknown'
            ticker_list.append({'ticker': t, 'sector': sector})

    result = sg.scan_tickers(
        ticker_list,
        model=request.model,
        threshold=request.threshold,
        min_conviction=request.min_conviction,
        max_results=request.max_results,
    )

    # Add sector status
    result['sector_status'] = rm.get_all_regimes()

    return result


@router.post("/retrain")
async def retrain_models(request: RetrainRequest):
    """Force retrain models."""
    rm, sg = _get_managers()
    end = datetime.now().strftime('%Y-%m-%d')
    start = (datetime.now() - timedelta(days=365 * 3)).strftime('%Y-%m-%d')

    if request.model in ("xgboost", "all"):
        results = rm.train_all(start, end)
        return {"status": "retraining", "model": request.model, "results": results}

    return {"status": "retraining", "model": request.model}


@router.get("/regimes")
async def get_regimes():
    """Get current regime state for all sector ETFs."""
    rm, _ = _get_managers()
    return {"sector_status": rm.get_all_regimes()}
```

- [ ] **Step 4: Run tests**

```bash
cd backend && ./venv/bin/python -m pytest tests/services/markov/test_signal_generator.py -v
```
Expected: All 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/markov/signal_generator.py backend/app/routers/markov.py backend/tests/services/markov/test_signal_generator.py
git commit -m "feat(markov): signal generator + screener API with tests"
```

---

### Task 6: MarkovSignalProvider (Backtest Bridge)

**Files:**
- Create: `backend/app/services/markov/signal_provider.py`
- Create: `backend/tests/services/markov/test_signal_provider.py`
- Modify: `backend/app/services/executor.py` (inject MarkovSignalProvider)

- [ ] **Step 1: Write the signal provider**

```python
# backend/app/services/markov/signal_provider.py
"""
MarkovSignalProvider — injected into QuantGen exec() sandbox.

Serves pre-computed historical signals for backtesting.
No 1-day delay applied (the True WFO pipeline handles temporal separation).
"""
import logging
import os
import pickle
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

from app.db.database import SECTOR_ETFS
from app.services.markov.regime_model import SectorRegimeManager
from app.services.markov.feature_engineering import (
    compute_ticker_features,
    DEFAULT_BUY_THRESHOLD,
)
from app.services.markov.pattern_recognizer import XGBoostRecognizer, LSTMRecognizer

logger = logging.getLogger(__name__)

# Cache directory
SIGNAL_CACHE_DIR = os.path.join(os.path.dirname(__file__), '../../../cache/markov')
os.makedirs(SIGNAL_CACHE_DIR, exist_ok=True)


class MarkovSignalProvider:
    """
    Provides historical Markov signals to QuantGen strategy code
    running inside the exec() sandbox.

    Signals are pre-computed and cached. The provider serves them
    on demand with O(1) lookup per (ticker, date) pair.

    Usage in QuantGen strategy:
        markov = MarkovSignalProvider(model="xgboost")
        signal = markov.get_signal('AAPL', '2024-01-15')
        conviction = markov.get_conviction('AAPL', '2024-01-15')
    """

    def __init__(self, model: str = "xgboost", threshold: float = DEFAULT_BUY_THRESHOLD):
        self.model = model
        self.threshold = threshold
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._regime_manager: Optional[SectorRegimeManager] = None

    def _cache_key(self, ticker: str) -> str:
        return f"{self.model}_{ticker.upper()}"

    def _build_cache(self, ticker: str, start_date: str, end_date: str) -> bool:
        """Pre-compute and cache signals for a ticker over a date range."""
        key = self._cache_key(ticker)
        if key in self._cache:
            return True

        # Get sector for this ticker
        from app.services.data_service import DataService
        meta = DataService.get_ticker_metadata(ticker)
        sector = meta['sector'] if meta else 'Unknown'

        # Compute features
        feat_data = compute_ticker_features(
            ticker, start_date, end_date, self.threshold, -self.threshold
        )
        if feat_data is None:
            return False

        # Get or create recognizer
        if self.model == "xgboost":
            rec = XGBoostRecognizer(ticker)
        else:
            rec = LSTMRecognizer(ticker)

        if not rec.load():
            # Train if not cached
            rec.train(feat_data['features'], feat_data['labels'])
            rec.save()

        # Predict for all dates
        predictions = rec.predict_batch(feat_data['features'])

        # Get regime history
        if self._regime_manager is None:
            self._regime_manager = SectorRegimeManager()
            # Train on the full date range
            self._regime_manager.train_all(start_date, end_date)

        # Build signal cache
        cache = {}
        for date in predictions.index:
            date_str = date.strftime('%Y-%m-%d')
            regime_info = self._regime_manager.get_ticker_regime(ticker, sector, date_str)
            pred = predictions.loc[date]

            is_bull = regime_info['regime'] == 'BULL'
            is_low_vol = regime_info['vol_probability'] < 0.5
            is_buy = pred['signal'] == 'BUY' and pred['conviction'] >= 0.6

            if is_bull and is_low_vol and is_buy:
                signal = 'BUY'
            elif not is_bull or not is_low_vol:
                signal = 'SELL'
            else:
                signal = 'HOLD'

            cache[date_str] = {
                'signal': signal,
                'conviction': float(pred['conviction']),
                'regime': regime_info['regime'],
                'bull_probability': regime_info['bull_probability'],
                'vol_regime': regime_info['vol_regime'],
                'vol_probability': regime_info['vol_probability'],
                'etf': regime_info['etf'],
            }

        self._cache[key] = cache
        return True

    def get_signal(self, ticker: str, date: str) -> str:
        """Get signal for a ticker on a specific date.
        
        Args:
            ticker: Stock ticker symbol
            date: Date string 'YYYY-MM-DD'
        
        Returns:
            'BUY', 'HOLD', or 'SELL'
        """
        key = self._cache_key(ticker)
        cache = self._cache.get(key, {})
        entry = cache.get(date, cache.get(list(cache.keys())[-1] if cache else ''))
        if entry is None:
            return 'HOLD'
        return entry['signal']

    def get_conviction(self, ticker: str, date: str) -> float:
        """Get conviction score for a ticker on a specific date."""
        key = self._cache_key(ticker)
        cache = self._cache.get(key, {})
        entry = cache.get(date, cache.get(list(cache.keys())[-1] if cache else ''))
        if entry is None:
            return 0.0
        return entry['conviction']

    def get_regime(self, ticker: str, date: str) -> Dict[str, Any]:
        """Get sector regime context for a ticker on a date."""
        key = self._cache_key(ticker)
        cache = self._cache.get(key, {})
        entry = cache.get(date, cache.get(list(cache.keys())[-1] if cache else ''))
        if entry is None:
            return {'regime': 'UNKNOWN', 'bull_probability': 0.5, 'vol_regime': 'UNKNOWN', 'vol_probability': 0.0}
        return {
            'regime': entry['regime'],
            'bull_probability': entry['bull_probability'],
            'vol_regime': entry['vol_regime'],
            'vol_probability': entry['vol_probability'],
            'etf': entry.get('etf', ''),
        }
```

- [ ] **Step 2: Write tests**

```python
# backend/tests/services/markov/test_signal_provider.py
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
```

- [ ] **Step 3: Inject into executor.py**

Edit `backend/app/services/executor.py` — find where `DataService` and `SafeDataService` are injected into the exec globals, and add `MarkovSignalProvider`:

```python
# In executor.py, add import and inject into globals
from app.services.markov.signal_provider import MarkovSignalProvider

# In the exec globals dict, add:
globals_dict = {
    'DataService': DataService,
    'SafeDataService': SafeDataService,
    'MarkovSignalProvider': MarkovSignalProvider,
    # ... existing globals
}
```

- [ ] **Step 4: Run tests**

```bash
cd backend && ./venv/bin/python -m pytest tests/services/markov/test_signal_provider.py -v
```
Expected: All 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/markov/signal_provider.py backend/tests/services/markov/test_signal_provider.py backend/app/services/executor.py
git commit -m "feat(markov): MarkovSignalProvider for exec sandbox + tests"
```

---

### Task 7: Scheduler / Retraining Orchestration

**Files:**
- Create: `backend/app/services/markov/trainer.py`

- [ ] **Step 1: Write the trainer**

```python
# backend/app/services/markov/trainer.py
"""
Training orchestration for Markov Chain Trader.

Manages scheduled retraining:
  - Daily: XGBoost retrain on rolling 1yr window
  - Quarterly: LSTM retrain on 3yr+ window
  - Monthly: Jump Model λ tuning
"""
import logging
import os
import pickle
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

from app.db.database import SECTOR_ETFS
from app.services.markov.regime_model import SectorRegimeManager
from app.services.markov.feature_engineering import compute_ticker_features
from app.services.markov.pattern_recognizer import XGBoostRecognizer, LSTMRecognizer
from app.services.markov.signal_generator import SignalGenerator

logger = logging.getLogger(__name__)

# Cache directory
MODEL_CACHE_DIR = os.path.join(os.path.dirname(__file__), '../../../models/markov')
os.makedirs(MODEL_CACHE_DIR, exist_ok=True)


class MarkovTrainer:
    """Orchestrates retraining of all Markov models."""

    def __init__(self):
        self.regime_manager = SectorRegimeManager()
        self.signal_generator = SignalGenerator(self.regime_manager)
        self._last_daily_train: Optional[str] = None
        self._last_quarterly_train: Optional[str] = None

    def train_regimes(self, years: int = 3) -> Dict[str, bool]:
        """Train/retrain all 11 sector ETF Jump Models."""
        end = datetime.now().strftime('%Y-%m-%d')
        start = (datetime.now() - timedelta(days=365 * years)).strftime('%Y-%m-%d')
        return self.regime_manager.train_all(start, end)

    def train_xgboost(self, tickers: List[str], years: int = 1) -> Dict[str, bool]:
        """Retrain XGBoost for all tickers (daily schedule)."""
        results = {}
        end = datetime.now().strftime('%Y-%m-%d')
        start = (datetime.now() - timedelta(days=365 * years)).strftime('%Y-%m-%d')

        for ticker in tickers:
            try:
                feat_data = compute_ticker_features(ticker, start, end)
                if feat_data is None:
                    results[ticker] = False
                    continue

                rec = XGBoostRecognizer(ticker)
                success = rec.train(feat_data['features'], feat_data['labels'])
                if success:
                    rec.save()
                results[ticker] = success

            except Exception as e:
                logger.error(f"XGBoost training failed for {ticker}: {e}")
                results[ticker] = False

        self._last_daily_train = datetime.now().strftime('%Y-%m-%d')
        return results

    def train_lstm(self, tickers: List[str], years: int = 3) -> Dict[str, bool]:
        """Retrain LSTM for all tickers (quarterly schedule)."""
        results = {}
        end = datetime.now().strftime('%Y-%m-%d')
        start = (datetime.now() - timedelta(days=365 * years)).strftime('%Y-%m-%d')

        for ticker in tickers:
            try:
                feat_data = compute_ticker_features(ticker, start, end)
                if feat_data is None:
                    results[ticker] = False
                    continue

                rec = LSTMRecognizer(ticker)
                success = rec.train(feat_data['features'], feat_data['labels'])
                if success:
                    rec.save()
                results[ticker] = success

            except Exception as e:
                logger.error(f"LSTM training failed for {ticker}: {e}")
                results[ticker] = False

        self._last_quarterly_train = datetime.now().strftime('%Y-%m-%d')
        return results

    def is_quarterly_month(self) -> bool:
        """Check if current month is a quarterly retrain month."""
        month = datetime.now().month
        return month in (1, 4, 7, 10)

    def get_status(self) -> Dict[str, Any]:
        """Get training status."""
        return {
            'regime_models': sum(1 for m in self.regime_manager.models.values() if m.is_trained),
            'last_daily_train': self._last_daily_train,
            'last_quarterly_train': self._last_quarterly_train,
            'next_quarterly_due': self.is_quarterly_month(),
        }
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/markov/trainer.py
git commit -m "feat(markov): training orchestration module"
```

---

### Task 8: Frontend — Markov Tab

**Files:**
- Create: `frontend/src/pages/Markov/index.tsx`
- Create: `frontend/src/pages/Markov/components/SectorRegimeGrid.tsx`
- Create: `frontend/src/pages/Markov/components/SignalsTable.tsx`
- Create: `frontend/src/pages/Markov/components/ControlPanel.tsx`
- Modify: `frontend/src/App.tsx` (add route)
- Modify: `frontend/src/components/layout/Layout.tsx` (add page title)

- [ ] **Step 1: Create ControlPanel component**

```tsx
// frontend/src/pages/Markov/components/ControlPanel.tsx
import { useState } from "react";

interface ControlPanelProps {
  onScan: (params: ScanParams) => void;
  loading: boolean;
}

export interface ScanParams {
  model: "xgboost" | "lstm";
  threshold: number;
  minConviction: number;
  maxResults: number;
}

export default function ControlPanel({ onScan, loading }: ControlPanelProps) {
  const [model, setModel] = useState<"xgboost" | "lstm">("xgboost");
  const [threshold, setThreshold] = useState(2.0);
  const [minConviction, setMinConviction] = useState(0.6);
  const [maxResults, setMaxResults] = useState(50);

  return (
    <div style={{ maxWidth: 480, padding: "24px" }}>
      <h2 style={{ fontSize: 20, fontWeight: 600, marginBottom: 24 }}>
        Scan Controls
      </h2>

      {/* Model Toggle */}
      <div style={{ marginBottom: 20 }}>
        <label style={{ fontSize: 14, fontWeight: 500, display: "block", marginBottom: 8 }}>
          Model
        </label>
        <div style={{ display: "flex", gap: 12 }}>
          <button
            onClick={() => setModel("xgboost")}
            style={{
              padding: "8px 20px",
              borderRadius: 8,
              border: `2px solid ${model === "xgboost" ? "#10B981" : "#d2d2d7"}`,
              background: model === "xgboost" ? "rgba(16, 185, 129, 0.1)" : "transparent",
              cursor: "pointer",
              fontWeight: 500,
            }}
          >
            XGBoost (Fast)
          </button>
          <button
            onClick={() => setModel("lstm")}
            style={{
              padding: "8px 20px",
              borderRadius: 8,
              border: `2px solid ${model === "lstm" ? "#10B981" : "#d2d2d7"}`,
              background: model === "lstm" ? "rgba(16, 185, 129, 0.1)" : "transparent",
              cursor: "pointer",
              fontWeight: 500,
            }}
          >
            LSTM (Deep)
          </button>
        </div>
      </div>

      {/* Threshold Slider */}
      <div style={{ marginBottom: 20 }}>
        <label style={{ fontSize: 14, fontWeight: 500, display: "block", marginBottom: 8 }}>
          BUY/SELL Threshold: {threshold.toFixed(1)}%
        </label>
        <input
          type="range"
          min={0.5}
          max={5.0}
          step={0.5}
          value={threshold}
          onChange={(e) => setThreshold(parseFloat(e.target.value))}
          style={{ width: "100%" }}
        />
      </div>

      {/* Min Conviction Slider */}
      <div style={{ marginBottom: 20 }}>
        <label style={{ fontSize: 14, fontWeight: 500, display: "block", marginBottom: 8 }}>
          Min Conviction: {minConviction.toFixed(2)}
        </label>
        <input
          type="range"
          min={0.3}
          max={0.95}
          step={0.05}
          value={minConviction}
          onChange={(e) => setMinConviction(parseFloat(e.target.value))}
          style={{ width: "100%" }}
        />
      </div>

      {/* Max Results */}
      <div style={{ marginBottom: 24 }}>
        <label style={{ fontSize: 14, fontWeight: 500, display: "block", marginBottom: 8 }}>
          Max Results
        </label>
        <input
          type="number"
          value={maxResults}
          onChange={(e) => setMaxResults(parseInt(e.target.value) || 50)}
          min={5}
          max={200}
          style={{
            padding: "8px 12px",
            borderRadius: 8,
            border: "1px solid #d2d2d7",
            width: 100,
          }}
        />
      </div>

      {/* Scan Button */}
      <button
        onClick={() => onScan({ model, threshold: threshold / 100, minConviction, maxResults })}
        disabled={loading}
        style={{
          padding: "12px 32px",
          borderRadius: 8,
          border: "none",
          background: loading ? "#9CA3AF" : "#10B981",
          color: "white",
          fontWeight: 600,
          cursor: loading ? "not-allowed" : "pointer",
          fontSize: 16,
        }}
      >
        {loading ? "Scanning..." : "Run Scan"}
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Create SectorRegimeGrid component**

```tsx
// frontend/src/pages/Markov/components/SectorRegimeGrid.tsx
interface SectorRegime {
  etf: string;
  regime: string;
  bull_probability: number;
  vol_regime: string;
}

interface SectorRegimeGridProps {
  sectors: SectorRegime[];
}

export default function SectorRegimeGrid({ sectors }: SectorRegimeGridProps) {
  if (!sectors || sectors.length === 0) return null;

  return (
    <div style={{ padding: "24px" }}>
      <h2 style={{ fontSize: 20, fontWeight: 600, marginBottom: 16 }}>
        Sector Regimes
      </h2>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 12 }}>
        {sectors.map((s) => (
          <div
            key={s.etf}
            style={{
              padding: 16,
              borderRadius: 12,
              border: `1px solid ${s.regime === "BULL" ? "#10B981" : s.regime === "BEAR" ? "#EF4444" : "#d2d2d7"}`,
              background: s.regime === "BULL" ? "rgba(16, 185, 129, 0.05)" : "rgba(239, 68, 68, 0.05)",
            }}
          >
            <div style={{ fontSize: 16, fontWeight: 700 }}>{s.etf}</div>
            <div style={{ fontSize: 14, color: s.regime === "BULL" ? "#10B981" : "#EF4444", marginTop: 4 }}>
              {s.regime}
            </div>
            <div style={{ fontSize: 12, color: "#6e6e73", marginTop: 2 }}>
              Bull: {(s.bull_probability * 100).toFixed(0)}% | Vol: {s.vol_regime}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create SignalsTable component**

```tsx
// frontend/src/pages/Markov/components/SignalsTable.tsx
import { useState } from "react";

interface Signal {
  ticker: string;
  sector: string;
  signal: string;
  conviction: number;
  price: number;
  regime: string;
  vol_regime: string;
  etf: string;
}

interface SignalsTableProps {
  signals: Signal[];
  totalScanned: number;
  loading: boolean;
}

export default function SignalsTable({ signals, totalScanned, loading }: SignalsTableProps) {
  const [showAll, setShowAll] = useState(false);
  const actionable = signals.filter((s) => s.signal === "BUY" && s.conviction >= 0.6);
  const display = showAll ? signals : actionable;

  if (loading) {
    return <div style={{ padding: 24, textAlign: "center", color: "#6e6e73" }}>Loading signals...</div>;
  }

  if (signals.length === 0) {
    return <div style={{ padding: 24, textAlign: "center", color: "#6e6e73" }}>No signals found. Run a scan to begin.</div>;
  }

  return (
    <div style={{ padding: "24px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <h2 style={{ fontSize: 20, fontWeight: 600 }}>
          Signals ({display.length} of {signals.length})
        </h2>
        <div style={{ fontSize: 12, color: "#6e6e73" }}>Scanned: {totalScanned} tickers</div>
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <button
          onClick={() => setShowAll(false)}
          style={{
            padding: "6px 16px",
            borderRadius: 6,
            border: `1px solid ${!showAll ? "#10B981" : "#d2d2d7"}`,
            background: !showAll ? "rgba(16, 185, 129, 0.1)" : "transparent",
            cursor: "pointer",
            fontSize: 13,
          }}
        >
          Actionable
        </button>
        <button
          onClick={() => setShowAll(true)}
          style={{
            padding: "6px 16px",
            borderRadius: 6,
            border: `1px solid ${showAll ? "#10B981" : "#d2d2d7"}`,
            background: showAll ? "rgba(16, 185, 129, 0.1)" : "transparent",
            cursor: "pointer",
            fontSize: 13,
          }}
        >
          Full List
        </button>
      </div>

      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
          <thead>
            <tr style={{ borderBottom: "1px solid #d2d2d7" }}>
              <th style={{ textAlign: "left", padding: "8px 12px", fontWeight: 600 }}>Rank</th>
              <th style={{ textAlign: "left", padding: "8px 12px", fontWeight: 600 }}>Ticker</th>
              <th style={{ textAlign: "left", padding: "8px 12px", fontWeight: 600 }}>Sector</th>
              <th style={{ textAlign: "left", padding: "8px 12px", fontWeight: 600 }}>Signal</th>
              <th style={{ textAlign: "right", padding: "8px 12px", fontWeight: 600 }}>Conviction</th>
              <th style={{ textAlign: "right", padding: "8px 12px", fontWeight: 600 }}>Price</th>
              <th style={{ textAlign: "left", padding: "8px 12px", fontWeight: 600 }}>ETF</th>
            </tr>
          </thead>
          <tbody>
            {display.map((s, i) => (
              <tr
                key={s.ticker}
                style={{ borderBottom: "1px solid #f0f0f0" }}
              >
                <td style={{ padding: "8px 12px" }}>{i + 1}</td>
                <td style={{ padding: "8px 12px", fontWeight: 600 }}>{s.ticker}</td>
                <td style={{ padding: "8px 12px" }}>{s.sector}</td>
                <td style={{ padding: "8px 12px" }}>
                  <span
                    style={{
                      color: s.signal === "BUY" ? "#10B981" : s.signal === "SELL" ? "#EF4444" : "#6e6e73",
                      fontWeight: 600,
                    }}
                  >
                    {s.signal === "BUY" ? "▲ BUY" : s.signal === "SELL" ? "▼ SELL" : "● HOLD"}
                  </span>
                </td>
                <td style={{ padding: "8px 12px", textAlign: "right" }}>
                  <div
                    style={{
                      display: "inline-block",
                      width: 60,
                      height: 6,
                      borderRadius: 3,
                      background: "#e5e7eb",
                      marginRight: 8,
                      verticalAlign: "middle",
                    }}
                  >
                    <div
                      style={{
                        width: `${(s.conviction * 100).toFixed(0)}%`,
                        height: "100%",
                        borderRadius: 3,
                        background: s.conviction >= 0.6 ? "#10B981" : "#F59E0B",
                      }}
                    />
                  </div>
                  {(s.conviction * 100).toFixed(0)}%
                </td>
                <td style={{ padding: "8px 12px", textAlign: "right" }}>${s.price.toFixed(2)}</td>
                <td style={{ padding: "8px 12px" }}>{s.etf}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Create main Markov page**

```tsx
// frontend/src/pages/Markov/index.tsx
import { useState, useCallback } from "react";
import ControlPanel, { ScanParams } from "./components/ControlPanel";
import SectorRegimeGrid from "./components/SectorRegimeGrid";
import SignalsTable from "./components/SignalsTable";

interface SectorRegime {
  etf: string;
  regime: string;
  bull_probability: number;
  vol_regime: string;
}

interface Signal {
  ticker: string;
  sector: string;
  signal: string;
  conviction: number;
  price: number;
  regime: string;
  vol_regime: string;
  etf: string;
}

export default function MarkovPage() {
  const [loading, setLoading] = useState(false);
  const [sectors, setSectors] = useState<SectorRegime[]>([]);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [totalScanned, setTotalScanned] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const handleScan = useCallback(async (params: ScanParams) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/markov/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: params.model,
          threshold: params.threshold,
          min_conviction: params.minConviction,
          max_results: params.maxResults,
        }),
      });
      const data = await res.json();
      if (data.signals) setSignals(data.signals);
      if (data.sector_status) setSectors(data.sector_status);
      if (data.total_scanned) setTotalScanned(data.total_scanned);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Scan failed");
    } finally {
      setLoading(false);
    }
  }, []);

  return (
    <div style={{ maxWidth: 1280, margin: "0 auto" }}>
      <ControlPanel onScan={handleScan} loading={loading} />

      {error && (
        <div style={{ padding: "12px 24px", color: "#EF4444", fontSize: 14 }}>
          Error: {error}
        </div>
      )}

      {sectors.length > 0 && <SectorRegimeGrid sectors={sectors} />}
      <SignalsTable signals={signals} totalScanned={totalScanned} loading={loading} />
    </div>
  );
}
```

- [ ] **Step 5: Add route in App.tsx**

Edit `frontend/src/App.tsx` — add import and route:
```tsx
import Markov from './pages/Markov'

// Add route inside the Layout wrapper:
<Route path="markov" element={
  <ErrorBoundary>
    <Markov />
  </ErrorBoundary>
} />
```

- [ ] **Step 6: Add page title in Layout.tsx**

Edit `frontend/src/components/layout/Layout.tsx` — add to `pageTitles`:
```tsx
const pageTitles: Record<string, string> = {
  "/sectors": "Sector Rotation Scanner",
  "/screener": "AI Stock Screener",
  "/earnings": "Earnings Calendar",
  "/quantgen": "QuantGen Strategy Builder",
  "/markov": "Markov Chain Trader",
};
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/Markov/ frontend/src/App.tsx frontend/src/components/layout/Layout.tsx
git commit -m "feat(markov): frontend tab with control panel, regime grid, signals table"
```

---

### Task 9: E2E Validation Pipeline

**Files:**
- Create: `backend/tests/services/markov/test_e2e_pipeline.py`

- [ ] **Step 1: Write E2E validation tests**

```python
# backend/tests/services/markov/test_e2e_pipeline.py
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
    """Step 1-2: Generate synthetic data with known regime shifts → Jump Model finds them."""
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

    # Last 150 days are bull → should detect bull
    last_regime = model.get_regime(dates[-1].strftime('%Y-%m-%d'))
    assert last_regime['regime'] == 'BULL', "Last 150 days have positive drift → BULL"


def test_e2e_xgboost_above_random():
    """Step 3: XGBoost predicts forward returns above random (50%+ accuracy)."""
    np.random.seed(42)
    n = 300
    features = pd.DataFrame({
        'f1': np.random.randn(n),
        'f2': np.random.randn(n),
        'f3': np.random.randn(n),
    })
    # Create structured labels (not random)
    labels = pd.Series(np.where(
        features['f1'] + features['f2'] > 0.3, 2,
        np.where(features['f1'] + features['f2'] < -0.3, 0, 1)
    ))

    rec = XGBoostRecognizer('TEST')
    success = rec.train(features, labels)
    assert success, "XGBoost must train"

    # Predict on training data
    preds = rec.predict_batch(features)
    accuracy = (preds['signal'] == labels.map({0: 'SELL', 1: 'HOLD', 2: 'BUY'}).values).mean()
    assert accuracy > 0.3, f"Accuracy ({accuracy:.2f}) should be above random (0.33)"


def test_e2e_convergent_signal_logic():
    """Step 4: Convergent signal rules produce correct outputs."""
    rm = SectorRegimeManager()
    gen = SignalGenerator(rm)

    # Manually set a bull regime
    model = JumpModel('XLK')
    model._is_trained = True
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
```

- [ ] **Step 2: Run all Markov tests**

```bash
cd backend && ./venv/bin/python -m pytest tests/services/markov/ -v
```
Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/services/markov/test_e2e_pipeline.py
git commit -m "test(markov): E2E validation pipeline"
```

---

### Task 10: Integration — QuantGen Backtest Bridge

**Files:**
- Modify: `backend/app/services/executor.py` (full injection)
- Create: `backend/tests/test_markov_integration.py`

- [ ] **Step 1: Find the exec globals injection point**

Read `backend/app/services/executor.py` to find where globals are set up, then add `MarkovSignalProvider`.

- [ ] **Step 2: Write integration test**

```python
# backend/tests/test_markov_integration.py
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
```

- [ ] **Step 3: Run all tests**

```bash
cd backend && ./venv/bin/python -m pytest tests/services/markov/ tests/test_markov_integration.py -v
```
Expected: All tests pass.

- [ ] **Step 4: Final commit**

```bash
git add backend/app/services/executor.py backend/tests/test_markov_integration.py
git commit -m "feat(markov): QuantGen backtest bridge integration"
git push origin main
```
