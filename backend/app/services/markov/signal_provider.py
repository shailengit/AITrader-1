"""
MarkovSignalProvider — injected into QuantGen exec() sandbox.

Serves pre-computed historical signals for backtesting.
No 1-day delay applied (the True WFO pipeline handles temporal separation).
"""
import logging
import os
from typing import Optional, Dict, Any

from app.services.markov.regime_model import SectorRegimeManager, VOL_GATE_THRESHOLD
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

    def __init__(self, model: str = "xgboost", threshold: float = DEFAULT_BUY_THRESHOLD,
                 min_conviction: float = 0.6, strict: bool = False):
        self.model = model
        self.threshold = threshold
        self.min_conviction = min_conviction
        self.strict = strict
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

        features = feat_data['features']
        if len(features) == 0:
            logger.warning(f"Empty feature DataFrame for {ticker}")
            return False

        # Get or create recognizer
        if self.model == "xgboost":
            rec = XGBoostRecognizer(ticker)
        else:
            rec = LSTMRecognizer(ticker)

        if not rec.load():
            # Train if not cached
            rec.train(features, feat_data['labels'])
            rec.save()

        # Predict for all dates
        predictions = rec.predict_batch(features)

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
            is_low_vol = regime_info['vol_probability'] < VOL_GATE_THRESHOLD
            is_high_conviction = pred['signal'] == 'BUY' and pred['conviction'] >= self.min_conviction

            if is_bull and is_low_vol and is_high_conviction:
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

    def _get_entry(self, ticker: str, date: str) -> Optional[Dict[str, Any]]:
        """Get cached entry for a ticker/date, with fallback to last known date."""
        key = self._cache_key(ticker)
        cache = self._cache.get(key, {})
        if date in cache:
            return cache[date]
        if cache:
            fallback_date = list(cache.keys())[-1]
            if self.strict:
                logger.error(f"Date {date} not in cache for {ticker} (strict=True)")
                return None
            logger.warning(f"Date {date} not in cache for {ticker}, using fallback {fallback_date}")
            return cache[fallback_date]
        return None

    def get_signal(self, ticker: str, date: str) -> str:
        """Get signal for a ticker on a specific date."""
        entry = self._get_entry(ticker, date)
        if entry is None:
            return 'HOLD'
        return entry['signal']

    def get_conviction(self, ticker: str, date: str) -> float:
        """Get conviction score for a ticker on a specific date."""
        entry = self._get_entry(ticker, date)
        if entry is None:
            return 0.0
        return entry['conviction']

    def get_regime(self, ticker: str, date: str) -> Dict[str, Any]:
        """Get sector regime context for a ticker on a date."""
        entry = self._get_entry(ticker, date)
        if entry is None:
            return {'regime': 'UNKNOWN', 'bull_probability': 0.5, 'vol_regime': 'UNKNOWN', 'vol_probability': 0.0}
        return {
            'regime': entry['regime'],
            'bull_probability': entry['bull_probability'],
            'vol_regime': entry['vol_regime'],
            'vol_probability': entry['vol_probability'],
            'etf': entry.get('etf', ''),
        }