"""
Training orchestration for Markov Chain Trader.

Manages scheduled retraining:
  - Daily: XGBoost retrain on rolling 1yr window
  - Quarterly: LSTM retrain on 3yr+ window
  - Monthly: Jump Model lambda tuning
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