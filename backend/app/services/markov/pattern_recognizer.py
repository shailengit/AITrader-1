"""
Pattern recognizer for Markov Chain Trader.

Two tracks:
  1. XGBoostRecognizer — gradient-boosted tree classifier (fast, interpretable)
  2. LSTMRecognizer    — PyTorch LSTM classifier (deep sequence model)

Both produce 3-class signals: BUY (2), HOLD (1), SELL (0).
"""
import logging
import pickle
from pathlib import Path
from typing import Dict, Any, Optional, List

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# Model cache directory
MODEL_DIR = Path(__file__).resolve().parents[3] / "models" / "markov"

# Label mapping
SIGNAL_MAP = {0: "SELL", 1: "HOLD", 2: "BUY"}


# ---------------------------------------------------------------------------
# XGBoost track
# ---------------------------------------------------------------------------

class XGBoostRecognizer:
    """XGBoost-based pattern recognizer.

    Trains a multi-class classifier on feature vectors to predict
    BUY / HOLD / SELL signals.  Models are cached to disk via pickle.
    """

    def __init__(self, ticker: str, model_dir: Optional[Path] = None):
        self.ticker = ticker
        self.model_dir = model_dir or MODEL_DIR
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self._model: Any = None
        self._is_trained = False

    # -- properties -------------------------------------------------------

    @property
    def is_trained(self) -> bool:
        return self._is_trained

    @property
    def _model_path(self) -> Path:
        return self.model_dir / f"xgb_{self.ticker}.pkl"

    # -- public API -------------------------------------------------------

    def train(
        self,
        features: pd.DataFrame,
        labels: pd.Series,
        **kwargs: Any,
    ) -> bool:
        """Train the XGBoost classifier.

        Args:
            features: DataFrame of feature columns (rows = samples).
            labels: Series of integer labels (0=SELL, 1=HOLD, 2=BUY).
            **kwargs: Passed to xgboost.XGBClassifier.

        Returns:
            True if training succeeded.
        """
        import xgboost as xgb

        if features.empty or labels.empty:
            logger.warning(f"Cannot train XGBoostRecognizer for {self.ticker}: empty data")
            return False

        try:
            params = {
                "n_estimators": kwargs.get("n_estimators", 100),
                "max_depth": kwargs.get("max_depth", 6),
                "learning_rate": kwargs.get("learning_rate", 0.1),
                "subsample": kwargs.get("subsample", 0.8),
                "colsample_bytree": kwargs.get("colsample_bytree", 0.8),
                "objective": "multi:softprob",
                "num_class": 3,
                "eval_metric": "mlogloss",
                "random_state": kwargs.get("random_state", 42),
                "verbosity": 0,
            }
            self._model = xgb.XGBClassifier(**params)
            self._model.fit(features.values, labels.values)
            self._is_trained = True
            logger.info(
                f"XGBoostRecognizer trained for {self.ticker}: "
                f"{len(features)} samples, {features.shape[1]} features"
            )
            return True

        except Exception as e:
            logger.error(
                f"XGBoostRecognizer training failed for {self.ticker}: {e}"
            )
            return False

    def predict(self, features: pd.Series) -> Dict[str, Any]:
        """Predict signal for a single feature vector.

        Args:
            features: A single-row Series of feature values.

        Returns:
            Dict with 'signal' (str), 'conviction' (float 0-1),
            and 'probabilities' (list of 3 floats).
        """
        if not self._is_trained or self._model is None:
            return {
                "signal": "HOLD",
                "conviction": 0.0,
                "probabilities": [1 / 3] * 3,
            }

        try:
            probs = self._model.predict_proba(features.values.reshape(1, -1))[0]
            pred_class = int(np.argmax(probs))
            conviction = float(probs[pred_class])
            return {
                "signal": SIGNAL_MAP[pred_class],
                "conviction": round(conviction, 4),
                "probabilities": [round(float(p), 4) for p in probs],
            }
        except Exception as e:
            logger.warning(f"XGBoostRecognizer predict failed for {self.ticker}: {e}")
            return {
                "signal": "HOLD",
                "conviction": 0.0,
                "probabilities": [1 / 3] * 3,
            }

    def predict_batch(self, features: pd.DataFrame) -> pd.DataFrame:
        """Predict signals for a batch of feature vectors.

        Args:
            features: DataFrame of feature columns (rows = samples).

        Returns:
            DataFrame with columns 'signal', 'conviction', and
            probability columns 'prob_0', 'prob_1', 'prob_2'.
        """
        if not self._is_trained or self._model is None:
            n = len(features)
            return pd.DataFrame({
                "signal": ["HOLD"] * n,
                "conviction": [0.0] * n,
                "prob_0": [1 / 3] * n,
                "prob_1": [1 / 3] * n,
                "prob_2": [1 / 3] * n,
            }, index=features.index)

        try:
            probs = self._model.predict_proba(features.values)
            pred_classes = np.argmax(probs, axis=1)
            convictions = probs[np.arange(len(probs)), pred_classes]
            return pd.DataFrame({
                "signal": [SIGNAL_MAP[c] for c in pred_classes],
                "conviction": convictions.round(4),
                "prob_0": probs[:, 0].round(4),
                "prob_1": probs[:, 1].round(4),
                "prob_2": probs[:, 2].round(4),
            }, index=features.index)
        except Exception as e:
            logger.warning(
                f"XGBoostRecognizer batch predict failed for {self.ticker}: {e}"
            )
            n = len(features)
            return pd.DataFrame({
                "signal": ["HOLD"] * n,
                "conviction": [0.0] * n,
                "prob_0": [1 / 3] * n,
                "prob_1": [1 / 3] * n,
                "prob_2": [1 / 3] * n,
            }, index=features.index)

    def save(self) -> bool:
        """Persist the trained model to disk.

        Returns:
            True if save succeeded.
        """
        if not self._is_trained or self._model is None:
            logger.warning(f"Cannot save untrained XGBoostRecognizer for {self.ticker}")
            return False

        try:
            self.model_dir.mkdir(parents=True, exist_ok=True)
            with open(self._model_path, "wb") as f:
                pickle.dump(self._model, f)
            logger.info(f"XGBoostRecognizer saved for {self.ticker}")
            return True
        except Exception as e:
            logger.error(f"Failed to save XGBoostRecognizer for {self.ticker}: {e}")
            return False

    def load(self) -> bool:
        """Load a previously saved model from disk.

        Returns:
            True if load succeeded.
        """
        path = self._model_path
        if not path.exists():
            logger.warning(f"No saved model found for {self.ticker} at {path}")
            return False

        try:
            with open(path, "rb") as f:
                self._model = pickle.load(f)
            self._is_trained = True
            logger.info(f"XGBoostRecognizer loaded for {self.ticker}")
            return True
        except Exception as e:
            logger.error(f"Failed to load XGBoostRecognizer for {self.ticker}: {e}")
            return False


# ---------------------------------------------------------------------------
# LSTM track (PyTorch)
# ---------------------------------------------------------------------------

class LSTMRecognizer:
    """PyTorch LSTM-based pattern recognizer.

    Uses a single-layer LSTM with a linear classification head.
    Models are cached to disk via pickle (state_dict + config).
    """

    def __init__(self, ticker: str, model_dir: Optional[Path] = None):
        self.ticker = ticker
        self.model_dir = model_dir or MODEL_DIR
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self._model: Any = None
        self._config: Dict[str, Any] = {}
        self._is_trained = False

    # -- properties -------------------------------------------------------

    @property
    def is_trained(self) -> bool:
        return self._is_trained

    @property
    def _model_path(self) -> Path:
        return self.model_dir / f"lstm_{self.ticker}.pkl"

    # -- public API -------------------------------------------------------

    def train(
        self,
        features: pd.DataFrame,
        labels: pd.Series,
        **kwargs: Any,
    ) -> bool:
        """Train the LSTM classifier.

        Args:
            features: DataFrame of feature columns (rows = samples).
            labels: Series of integer labels (0=SELL, 1=HOLD, 2=BUY).
            **kwargs: Override defaults (hidden_size, num_layers, dropout,
                      epochs, lr, batch_size, seq_length).

        Returns:
            True if training succeeded.
        """
        import torch
        import torch.nn as nn
        import torch.optim as optim
        from torch.utils.data import DataLoader, TensorDataset

        if features.empty or labels.empty:
            logger.warning(f"Cannot train LSTMRecognizer for {self.ticker}: empty data")
            return False

        try:
            n_features = features.shape[1]
            hidden_size = kwargs.get("hidden_size", 64)
            num_layers = kwargs.get("num_layers", 1)
            dropout = kwargs.get("dropout", 0.2)
            epochs = kwargs.get("epochs", 50)
            lr = kwargs.get("lr", 1e-3)
            batch_size = kwargs.get("batch_size", 32)
            seq_length = kwargs.get("seq_length", 10)

            # Store config for serialization
            self._config = {
                "n_features": n_features,
                "hidden_size": hidden_size,
                "num_layers": num_layers,
                "dropout": dropout,
                "seq_length": seq_length,
            }

            # Build sequences
            X, y = self._build_sequences(
                features.values, labels.values, seq_length
            )
            if len(X) < 10:
                logger.warning(
                    f"Too few LSTM sequences for {self.ticker}: {len(X)}"
                )
                return False

            # Model
            self._model = _LSTMClassifier(
                n_features, hidden_size, num_layers, dropout
            )
            criterion = nn.CrossEntropyLoss()
            optimizer = optim.Adam(self._model.parameters(), lr=lr)

            # DataLoader
            dataset = TensorDataset(
                torch.tensor(X, dtype=torch.float32),
                torch.tensor(y, dtype=torch.long),
            )
            loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)

            # Training loop
            self._model.train()
            for epoch in range(epochs):
                total_loss = 0.0
                for batch_X, batch_y in loader:
                    optimizer.zero_grad()
                    outputs = self._model(batch_X)
                    loss = criterion(outputs, batch_y)
                    loss.backward()
                    optimizer.step()
                    total_loss += loss.item()

                if (epoch + 1) % 10 == 0:
                    logger.debug(
                        f"LSTM epoch {epoch + 1}/{epochs} — loss: {total_loss:.4f}"
                    )

            self._is_trained = True
            logger.info(
                f"LSTMRecognizer trained for {self.ticker}: "
                f"{len(X)} sequences, {n_features} features"
            )
            return True

        except Exception as e:
            logger.error(
                f"LSTMRecognizer training failed for {self.ticker}: {e}"
            )
            return False

    def predict(self, features: pd.Series) -> Dict[str, Any]:
        """Predict signal for a single feature vector.

        Args:
            features: A single-row Series of feature values.

        Returns:
            Dict with 'signal' (str), 'conviction' (float 0-1),
            and 'probabilities' (list of 3 floats).
        """
        if not self._is_trained or self._model is None:
            return {
                "signal": "HOLD",
                "conviction": 0.0,
                "probabilities": [1 / 3] * 3,
            }

        import torch
        import torch.nn.functional as F

        try:
            self._model.eval()
            seq_length = self._config.get("seq_length", 10)
            # Pad/truncate to seq_length
            vals = features.values[-seq_length:]
            if len(vals) < seq_length:
                pad = np.zeros(seq_length - len(vals))
                vals = np.concatenate([pad, vals])
            x = torch.tensor(vals, dtype=torch.float32).view(1, seq_length, -1)

            with torch.no_grad():
                logits = self._model(x)
                probs = F.softmax(logits, dim=1).numpy()[0]

            pred_class = int(np.argmax(probs))
            conviction = float(probs[pred_class])
            return {
                "signal": SIGNAL_MAP[pred_class],
                "conviction": round(conviction, 4),
                "probabilities": [round(float(p), 4) for p in probs],
            }
        except Exception as e:
            logger.warning(f"LSTMRecognizer predict failed for {self.ticker}: {e}")
            return {
                "signal": "HOLD",
                "conviction": 0.0,
                "probabilities": [1 / 3] * 3,
            }

    def save(self) -> bool:
        """Persist the trained model to disk.

        Returns:
            True if save succeeded.
        """
        if not self._is_trained or self._model is None:
            logger.warning(f"Cannot save untrained LSTMRecognizer for {self.ticker}")
            return False

        try:
            self.model_dir.mkdir(parents=True, exist_ok=True)
            payload = {
                "state_dict": self._model.state_dict(),
                "config": self._config,
            }
            with open(self._model_path, "wb") as f:
                pickle.dump(payload, f)
            logger.info(f"LSTMRecognizer saved for {self.ticker}")
            return True
        except Exception as e:
            logger.error(f"Failed to save LSTMRecognizer for {self.ticker}: {e}")
            return False

    def load(self) -> bool:
        """Load a previously saved model from disk.

        Returns:
            True if load succeeded.
        """
        path = self._model_path
        if not path.exists():
            logger.warning(f"No saved LSTM model found for {self.ticker} at {path}")
            return False

        import torch

        try:
            with open(path, "rb") as f:
                payload = pickle.load(f)

            self._config = payload["config"]
            self._model = _LSTMClassifier(
                n_features=self._config["n_features"],
                hidden_size=self._config["hidden_size"],
                num_layers=self._config["num_layers"],
                dropout=self._config["dropout"],
            )
            self._model.load_state_dict(payload["state_dict"])
            self._model.eval()
            self._is_trained = True
            logger.info(f"LSTMRecognizer loaded for {self.ticker}")
            return True
        except Exception as e:
            logger.error(f"Failed to load LSTMRecognizer for {self.ticker}: {e}")
            return False

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _build_sequences(
        X: np.ndarray, y: np.ndarray, seq_length: int
    ) -> tuple:
        """Build (seq_length, n_features) sequences from flat arrays."""
        X_seq, y_seq = [], []
        for i in range(len(X) - seq_length):
            X_seq.append(X[i : i + seq_length])
            y_seq.append(y[i + seq_length])
        return np.array(X_seq), np.array(y_seq)


# ---------------------------------------------------------------------------
# Internal PyTorch module
# ---------------------------------------------------------------------------

class _LSTMClassifier:
    """Minimal single-layer LSTM with a linear classification head."""

    def __init__(
        self,
        n_features: int,
        hidden_size: int = 64,
        num_layers: int = 1,
        dropout: float = 0.2,
    ):
        import torch
        import torch.nn as nn

        self.lstm = nn.LSTM(
            input_size=n_features,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0,
        )
        self.classifier = nn.Linear(hidden_size, 3)
        self.dropout = nn.Dropout(dropout)

    def train(self, mode: bool = True):
        import torch.nn as nn
        self.lstm.train(mode)
        self.classifier.train(mode)
        self.dropout.train(mode)

    def eval(self):
        self.train(False)

    def parameters(self):
        return list(self.lstm.parameters()) + list(self.classifier.parameters())

    def state_dict(self):
        return {
            "lstm": self.lstm.state_dict(),
            "classifier": self.classifier.state_dict(),
        }

    def load_state_dict(self, state_dict: dict):
        self.lstm.load_state_dict(state_dict["lstm"])
        self.classifier.load_state_dict(state_dict["classifier"])

    def __call__(self, x):
        import torch.nn.functional as F
        lstm_out, _ = self.lstm(x)
        last_out = lstm_out[:, -1, :]
        dropped = self.dropout(last_out)
        return self.classifier(dropped)
