"""
3-State Hidden Markov Model for regime detection.

Trained on SPY daily returns + VIX level + 200-day MA slope.
Maps states to Bull/Sideways/Crisis regimes with walk-forward retraining.
"""
import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta

import pandas as pd
import numpy as np
from hmmlearn import hmm

from app.db.database import engine
from sqlalchemy import text

logger = logging.getLogger(__name__)

# State definitions
STATE_NAMES = {0: "CRISIS", 1: "SIDEWAYS", 2: "BULL"}

# Regime-specific parameters
REGIME_PARAMS = {
    "CRISIS": {
        "max_holdings": 3,
        "trailing_stop_pct": 0.10,  # Fixed 10% stop
        "sizing_mult": 0.40,
        "min_hold_days": 5,
        "use_atr_stop": False,
    },
    "SIDEWAYS": {
        "max_holdings": 4,
        "trailing_stop_pct": 0.15,  # Fixed 15% stop
        "sizing_mult": 0.70,
        "min_hold_days": 7,
        "use_atr_stop": False,
    },
    "BULL": {
        "max_holdings": 5,
        "trailing_stop_pct": None,  # Use ATR-based dynamic stop
        "sizing_mult": 1.0,
        "min_hold_days": 10,
        "use_atr_stop": True,
    },
}


def get_spy_returns(start_date: str, end_date: str) -> pd.Series:
    """Get SPY daily log returns."""
    with engine.connect() as conn:
        df = pd.read_sql(
            'SELECT "Date", "Close" FROM spy '
            f'WHERE "Date" >= \'{start_date}\' AND "Date" <= \'{end_date}\' '
            'ORDER BY "Date"',
            conn,
        )
    if df.empty:
        return pd.Series(dtype=float)
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date")
    returns = np.log(df["Close"] / df["Close"].shift(1)).dropna()
    return returns


def get_vix_levels(start_date: str, end_date: str) -> pd.Series:
    """Get VIX closing levels."""
    with engine.connect() as conn:
        df = pd.read_sql(
            'SELECT "Date", "Close" FROM vix '
            f'WHERE "Date" >= \'{start_date}\' AND "Date" <= \'{end_date}\' '
            'ORDER BY "Date"',
            conn,
        )
    if df.empty:
        return pd.Series(dtype=float)
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date")
    return df["Close"].astype(float)


def get_spy_ma200_slope(start_date: str, end_date: str) -> pd.Series:
    """Get SPY 200-day MA slope (rate of change)."""
    with engine.connect() as conn:
        df = pd.read_sql(
            'SELECT "Date", "Close" FROM spy '
            f'WHERE "Date" >= \'{start_date}\' AND "Date" <= \'{end_date}\' '
            'ORDER BY "Date"',
            conn,
        )
    if df.empty:
        return pd.Series(dtype=float)
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date")
    close = df["Close"]
    ma200 = close.rolling(window=200).mean()
    # Slope = (MA200[t] - MA200[t-20]) / MA200[t-20] (20-day rate of change)
    slope = ma200.pct_change(periods=20)
    return slope


def build_hmm_features(start_date: str, end_date: str) -> Optional[pd.DataFrame]:
    """Build feature matrix for HMM training.

    Features:
    1. SPY daily log returns
    2. VIX level (normalized)
    3. SPY 200-day MA slope

    Returns DataFrame aligned on dates, or None if insufficient data.
    """
    returns = get_spy_returns(start_date, end_date)
    vix = get_vix_levels(start_date, end_date)
    ma_slope = get_spy_ma200_slope(start_date, end_date)

    if returns.empty:
        logger.warning("No SPY returns data available for HMM training")
        return None

    # Align all series
    features = pd.DataFrame({"returns": returns})
    features["vix"] = vix
    features["ma200_slope"] = ma_slope

    # Drop NaN rows (from MA200 computation)
    features = features.dropna()

    if len(features) < 60:
        logger.warning(f"Insufficient HMM training data: {len(features)} rows")
        return None

    return features


class HMMRegimeModel:
    """3-state Hidden Markov Model for market regime detection.

    Trained on SPY returns + VIX + MA200 slope.
    Uses walk-forward retraining (3-year windows, retrain every 180 days).
    """

    def __init__(self, n_states: int = 3, n_iter: int = 1000, random_state: int = 42):
        self.n_states = n_states
        self.n_iter = n_iter
        self.random_state = random_state
        self.model: Optional[hmm.GaussianHMM] = None
        self._is_trained = False
        self._feature_index: Optional[pd.DatetimeIndex] = None
        self._state_sequence: Optional[np.ndarray] = None
        self._state_map: Dict[int, str] = {}  # Maps HMM state index -> regime name
        self._training_data: Optional[np.ndarray] = None  # Store training data for predict_proba

    @property
    def is_trained(self) -> bool:
        return self._is_trained

    def train(self, features: pd.DataFrame) -> bool:
        """Train the HMM on feature matrix.

        Args:
            features: DataFrame with columns ['returns', 'vix', 'ma200_slope']

        Returns:
            True if training succeeded
        """
        if features is None or len(features) < 60:
            logger.warning("Insufficient features for HMM training")
            return False

        try:
            # Prepare observation matrix (n_samples x n_features)
            X = features[["returns", "vix", "ma200_slope"]].values

            # Fit Gaussian HMM with 3 states
            self.model = hmm.GaussianHMM(
                n_components=self.n_states,
                covariance_type="full",
                n_iter=self.n_iter,
                random_state=self.random_state,
                tol=1e-4,
            )
            self.model.fit(X)

            # Decode the most likely state sequence
            self._state_sequence = self.model.predict(X)
            self._feature_index = features.index
            self._training_data = X  # Store for predict_proba

            # Map HMM state indices to regime names based on mean returns
            self._map_states_to_regimes(features)

            self._is_trained = True
            logger.info(
                f"HMM trained: {len(features)} observations, "
                f"states: {self._state_map}"
            )
            return True

        except Exception as e:
            logger.error(f"HMM training failed: {e}")
            return False

    def _map_states_to_regimes(self, features: pd.DataFrame) -> None:
        """Map HMM state indices to regime names based on mean return and VIX.

        State with highest mean return + lowest mean VIX → BULL
        State with lowest mean return + highest mean VIX → CRISIS
        Middle state → SIDEWAYS
        """
        X = features[["returns", "vix", "ma200_slope"]].values
        states = self._state_sequence

        state_stats = {}
        for s in range(self.n_states):
            mask = states == s
            if mask.sum() == 0:
                continue
            mean_ret = float(np.mean(X[mask, 0]))
            mean_vix = float(np.mean(X[mask, 1]))
            mean_slope = float(np.mean(X[mask, 2]))
            state_stats[s] = {
                "mean_return": mean_ret,
                "mean_vix": mean_vix,
                "mean_slope": mean_slope,
            }

        # Score: higher return + lower VIX + higher slope = more bullish
        def bullish_score(s):
            stats = state_stats.get(s, {})
            return stats.get("mean_return", 0) - stats.get("mean_vix", 20) * 0.001 + stats.get("mean_slope", 0)

        sorted_states = sorted(state_stats.keys(), key=bullish_score)

        # Lowest score → CRISIS, middle → SIDEWAYS, highest → BULL
        if len(sorted_states) >= 3:
            self._state_map[sorted_states[0]] = "CRISIS"
            self._state_map[sorted_states[1]] = "SIDEWAYS"
            self._state_map[sorted_states[2]] = "BULL"
        elif len(sorted_states) == 2:
            self._state_map[sorted_states[0]] = "CRISIS"
            self._state_map[sorted_states[1]] = "BULL"
        else:
            self._state_map[sorted_states[0]] = "BULL"

        logger.info(f"State mapping: {self._state_map}")
        for s, stats in state_stats.items():
            logger.info(
                f"  State {s} ({self._state_map.get(s, '?')}): "
                f"mean_ret={stats['mean_return']:.6f}, "
                f"mean_vix={stats['mean_vix']:.1f}, "
                f"mean_slope={stats['mean_slope']:.6f}"
            )

    def get_regime(self, date: Optional[str] = None) -> Dict[str, Any]:
        """Get regime state for a given date.

        Args:
            date: Date string 'YYYY-MM-DD'. If None, returns latest.

        Returns:
            Dict with regime, state_name, and state probabilities
        """
        if not self._is_trained or self._feature_index is None:
            return {
                "regime": "BULL",
                "state_name": "BULL",
                "state_index": 2,
                "probabilities": [0.0, 0.0, 1.0],
            }

        if date is not None:
            target = pd.Timestamp(date)
            # Find nearest date <= target
            mask = self._feature_index <= target
            if mask.sum() == 0:
                # Before training data, default to BULL
                return {
                    "regime": "BULL",
                    "state_name": "BULL",
                    "state_index": 2,
                    "probabilities": [0.0, 0.0, 1.0],
                }
            idx = self._feature_index[mask][-1]
            pos = self._feature_index.get_loc(idx)
        else:
            pos = -1
            idx = self._feature_index[-1]

        state_idx = int(self._state_sequence[pos])
        regime_name = self._state_map.get(state_idx, "BULL")

        # Get state probabilities (posterior)
        if self.model is not None and self._training_data is not None:
            probs = self.model.predict_proba(self._training_data)
            state_probs = [float(p) for p in probs[pos]]
        else:
            state_probs = [0.0, 0.0, 0.0]
            state_probs[state_idx] = 1.0

        return {
            "regime": regime_name,
            "state_name": regime_name,
            "state_index": state_idx,
            "probabilities": state_probs,
        }

    def get_regime_params(self, date: Optional[str] = None) -> Dict[str, Any]:
        """Get regime-specific trading parameters for a given date.

        Returns dict with max_holdings, trailing_stop_pct, sizing_mult, min_hold_days.
        """
        regime_info = self.get_regime(date)
        regime_name = regime_info["regime"]
        params = REGIME_PARAMS.get(regime_name, REGIME_PARAMS["BULL"])
        return {
            **params,
            "regime": regime_name,
            "state_index": regime_info["state_index"],
            "probabilities": regime_info["probabilities"],
        }


class HMMRegimeManager:
    """Manages walk-forward HMM regime models.

    Trains a new HMM every 180 days on rolling 3-year windows.
    """

    def __init__(self, n_states: int = 3, n_iter: int = 1000):
        self.n_states = n_states
        self.n_iter = n_iter
        self.models: Dict[str, HMMRegimeModel] = {}  # date -> model
        self.retrain_dates: List[str] = []

    def train_walk_forward(
        self, start_date: str, end_date: str, retrain_interval_days: int = 180
    ) -> None:
        """Train HMM models on rolling 3-year windows.

        Args:
            start_date: Start of the backtest period
            end_date: End of the backtest period
            retrain_interval_days: How often to retrain (default 180)
        """
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        # Generate retrain dates
        d = start_dt + timedelta(days=3 * 365)
        while d < end_dt:
            self.retrain_dates.append(d.strftime("%Y-%m-%d"))
            d += timedelta(days=retrain_interval_days)

        if not self.retrain_dates:
            self.retrain_dates.append(end_date)

        for i, rd in enumerate(self.retrain_dates):
            train_start = (
                datetime.strptime(rd, "%Y-%m-%d") - timedelta(days=3 * 365 + 35)
            ).strftime("%Y-%m-%d")
            logger.info(f"HMM Model #{i+1}: {train_start} → {rd}")

            features = build_hmm_features(train_start, rd)
            if features is None:
                logger.warning(f"Cannot build features for {train_start} → {rd}")
                continue

            model = HMMRegimeModel(
                n_states=self.n_states, n_iter=self.n_iter
            )
            if model.train(features):
                self.models[rd] = model

    def get_regime(self, date: str) -> Dict[str, Any]:
        """Get regime for a given date using the most recent model."""
        if not self.models:
            return {
                "regime": "BULL",
                "state_name": "BULL",
                "state_index": 2,
                "probabilities": [0.0, 0.0, 1.0],
            }

        # Find the most recent model trained before this date
        model_date = None
        for rd in sorted(self.models.keys()):
            if rd <= date:
                model_date = rd
            else:
                break

        if model_date is None:
            # Use the earliest model
            model_date = sorted(self.models.keys())[0]

        model = self.models[model_date]
        return model.get_regime(date)

    def get_regime_params(self, date: str) -> Dict[str, Any]:
        """Get regime-specific trading parameters for a given date."""
        regime_info = self.get_regime(date)
        regime_name = regime_info["regime"]
        params = REGIME_PARAMS.get(regime_name, REGIME_PARAMS["BULL"])
        return {
            **params,
            "regime": regime_name,
            "state_index": regime_info["state_index"],
            "probabilities": regime_info["probabilities"],
        }
