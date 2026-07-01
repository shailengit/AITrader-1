"""Tests for backtest position-sizing helpers."""
import pytest
from app.services.backtest.sizing import (
    compute_position_dollars,
    SizingMode,
    SizingError,
)


def test_equal_weight_divides_capital_evenly():
    out = compute_position_dollars("equal_weight", n=20, scores=None, vols=None)
    assert len(out) == 20
    assert all(d == 5000.0 for d in out)
    assert sum(out) == pytest.approx(100_000.0)


def test_equal_weight_with_cap_respects_per_position_cap():
    out = compute_position_dollars(
        "capital_capped", n=20, scores=None, vols=None, per_position_cap=4000.0
    )
    assert all(d == 4000.0 for d in out)
    # Capital NOT fully deployed — 80k of 100k, 20k sits idle
    assert sum(out) == pytest.approx(80_000.0)


def test_score_weighted_proportional_to_scores():
    scores = [10.0, 30.0, 60.0]  # sum = 100
    out = compute_position_dollars("score_weighted", n=3, scores=scores, vols=None)
    assert out[0] == pytest.approx(10_000.0)
    assert out[1] == pytest.approx(30_000.0)
    assert out[2] == pytest.approx(60_000.0)
    assert sum(out) == pytest.approx(100_000.0)


def test_inverse_vol_weights_lower_vol_higher():
    vols = [0.10, 0.40]  # 1/vol = [10.0, 2.5]; sum = 12.5
    out = compute_position_dollars("inverse_vol", n=2, scores=None, vols=vols)
    # ticker 0 gets 10/12.5 = 80% of capital
    assert out[0] == pytest.approx(80_000.0)
    assert out[1] == pytest.approx(20_000.0)


def test_unknown_mode_raises():
    with pytest.raises(SizingError):
        compute_position_dollars("not_a_mode", n=5, scores=None, vols=None)


def test_inverse_vol_requires_vols():
    with pytest.raises(SizingError):
        compute_position_dollars("inverse_vol", n=5, scores=None, vols=None)


def test_score_weighted_requires_scores():
    with pytest.raises(SizingError):
        compute_position_dollars("score_weighted", n=5, scores=None, vols=None)


def test_zero_vol_raises():
    with pytest.raises(SizingError):
        compute_position_dollars("inverse_vol", n=2, scores=None, vols=[0.0, 0.5])


def test_negative_n_raises():
    with pytest.raises(SizingError):
        compute_position_dollars("equal_weight", n=0, scores=None, vols=None)
