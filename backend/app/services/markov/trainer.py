"""
Training orchestration for Markov Chain Trader.

Manages scheduled retraining:
  - Daily: XGBoost retrain on rolling 1yr window
  - Quarterly: LSTM retrain on 3yr+ window
  - Monthly: Jump Model lambda tuning
"""
import logging
from typing import Dict, Any, List, Optional, Type, Union
from datetime import datetime, timedelta

from app.services.markov.regime_model import SectorRegimeManager
from app.services.markov.feature_engineering import compute_ticker_features
from app.services.markov.pattern_recognizer import XGBoostRecognizer, LSTMRecognizer

logger = logging.getLogger(__name__)


class MarkovTrainer:
    """Orchestrates retraining of all Markov models."""

    LOG_INTERVAL = 100  # Log progress every N tickers

    def __init__(self):
        self.regime_manager = SectorRegimeManager()
        self._last_daily_train: Optional[str] = None
        self._last_quarterly_train: Optional[str] = None

    @staticmethod
    def _date_range(years: int) -> tuple[str, str]:
        """Compute (start, end) date strings for a lookback window."""
        end = datetime.now().strftime('%Y-%m-%d')
        start = (datetime.now() - timedelta(days=365 * years)).strftime('%Y-%m-%d')
        return start, end

    def _train_recognizer(self, tickers: List[str], years: int,
                          recognizer_cls: Type[Union[XGBoostRecognizer, LSTMRecognizer]],
                          label: str) -> Dict[str, bool]:
        """Train recognizers for a batch of tickers.

        Args:
            tickers: List of ticker symbols to train.
            years: Number of years of lookback data.
            recognizer_cls: Recognizer class (XGBoostRecognizer or LSTMRecognizer).
            label: Human-readable label for logging (e.g., "XGBoost").

        Returns:
            Dict mapping ticker to training success boolean.
        """
        results = {}
        start, end = self._date_range(years)

        for i, ticker in enumerate(tickers):
            try:
                feat_data = compute_ticker_features(ticker, start, end)
                if feat_data is None:
                    results[ticker] = False
                    continue

                rec = recognizer_cls(ticker)
                success = rec.train(feat_data['features'], feat_data['labels'])
                if success:
                    rec.save()
                results[ticker] = success

                if (i + 1) % self.LOG_INTERVAL == 0:
                    logger.info(f"{label} training: {i + 1}/{len(tickers)} tickers done")

            except Exception as e:
                logger.error(f"{label} training failed for {ticker}: {e}")
                results[ticker] = False

        return results

    def train_regimes(self, years: int = 3) -> Dict[str, bool]:
        """Train/retrain all 11 sector ETF Jump Models."""
        start, end = self._date_range(years)
        return self.regime_manager.train_all(start, end)

    def train_xgboost(self, tickers: List[str], years: int = 1) -> Dict[str, bool]:
        """Retrain XGBoost for all tickers (daily schedule)."""
        results = self._train_recognizer(tickers, years, XGBoostRecognizer, "XGBoost")
        self._last_daily_train = datetime.now().strftime('%Y-%m-%d')
        return results

    def train_lstm(self, tickers: List[str], years: int = 3) -> Dict[str, bool]:
        """Retrain LSTM for all tickers (quarterly schedule)."""
        results = self._train_recognizer(tickers, years, LSTMRecognizer, "LSTM")
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