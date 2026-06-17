"""
Convergent signal generator for Markov Chain Trader.

Combines regime state + pattern recognizer output into BUY/HOLD/SELL
with conviction score. Applies 1-day trading delay for live signals.
"""
import logging
import time
from typing import Optional, Dict, Any, List, Callable
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

        # Convergence rules — Option A: sector regime no longer blocks BUY
        is_low_vol = regime_info['vol_probability'] < VOL_GATE_THRESHOLD
        is_high_conviction = pred['conviction'] >= min_conviction

        if is_low_vol and pred['signal'] == 'BUY' and is_high_conviction:
            signal = 'BUY'
        elif not is_low_vol:
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
                    max_results: int = 50,
                    max_tickers: int = 50,
                    end_date: Optional[str] = None,
                    progress_callback=None) -> Dict[str, Any]:
        """Scan multiple tickers and return ranked signals.

        Args:
            tickers: List of dicts with 'ticker' and 'sector' keys
            model: 'xgboost' or 'lstm'
            threshold: BUY/SELL threshold for label generation
            min_conviction: Minimum conviction to act
            max_results: Max results to return
            max_tickers: Max tickers to process (capped to keep first-scan
                         response time reasonable when training on the fly).
            end_date: Optional scan end date (YYYY-MM-DD). Defaults to today.
            progress_callback: Optional callable(pct, ticker, action, completed, total, elapsed, eta)

        Returns:
            Dict with signals list and metadata
        """
        results = []
        errors = 0

        # Cap tickers to keep first-scan response time manageable
        tickers = tickers[:max_tickers]
        total = len(tickers)
        start_time = time.time()

        for idx, item in enumerate(tickers):
            try:
                # Report progress
                if progress_callback:
                    elapsed = time.time() - start_time
                    pct = (idx / total) * 100 if total > 0 else 0
                    # Estimate: use average time per completed ticker
                    avg_per_ticker = elapsed / max(idx, 1)
                    eta = avg_per_ticker * (total - idx)
                    progress_callback(
                        pct=pct,
                        ticker=item['ticker'],
                        action="Computing features & training model..." if model == "lstm" else "Computing features...",
                        completed=idx,
                        total=total,
                        elapsed=elapsed,
                        eta=eta,
                    )
                end = end_date if end_date else datetime.now().strftime('%Y-%m-%d')
                # Compute start relative to end_date so the data window always
                # spans ~400 calendar days (~252 trading days).  When end_date
                # is in the past this ensures the lookback has enough data.
                end_dt = datetime.strptime(end, '%Y-%m-%d')
                start = (end_dt - timedelta(days=400)).strftime('%Y-%m-%d')

                feat_data = compute_ticker_features(
                    item['ticker'], start, end, threshold, -threshold,
                    min_rows=1  # Scanning only needs the latest feature row
                )
                if feat_data is None:
                    errors += 1
                    continue

                # Train recognizer on the fly if no cached model exists
                rec = self._get_recognizer(item['ticker'], model)
                if not rec.is_trained and feat_data['labels'] is not None:
                    try:
                        train_success = rec.train(feat_data['features'], feat_data['labels'])
                        if train_success:
                            rec.save()
                    except Exception as train_err:
                        logger.debug(f"On-the-fly training failed for {item['ticker']}: {train_err}")

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

        # Final progress: 100% complete
        if progress_callback:
            elapsed = time.time() - start_time
            progress_callback(
                pct=100.0,
                ticker="",
                action="Complete",
                completed=total,
                total=total,
                elapsed=elapsed,
                eta=0.0,
            )

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
