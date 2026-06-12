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
