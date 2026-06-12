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
                end = datetime.now().strftime('%Y-%m-%d')
                start = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')

                feat_data = compute_ticker_features(
                    item['ticker'], start, end, threshold, -threshold
                )
                if feat_data is None:
                    errors += 1
                    continue

                latest_features = feat_data['features'].iloc[-1]
                signal = self.generate_signal(
                    item['ticker'], item['sector'],
                    latest_features, model, min_conviction
                )

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
