"""Tests for strategy signal generation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tickline.strategies import SMACrossover, RSIMeanReversion


def _synthetic_ohlcv(n: int = 200, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = rng.normal(loc=0.0005, scale=0.01, size=n)
    close = 100.0 * np.exp(np.cumsum(returns))
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.005,
            "low": close * 0.995,
            "close": close,
            "volume": rng.uniform(100, 1000, size=n),
        },
        index=idx,
    )


def test_sma_rejects_bad_periods():
    with pytest.raises(ValueError):
        SMACrossover(fast=50, slow=20)


def test_sma_positions_in_valid_range():
    df = _synthetic_ohlcv()
    pos = SMACrossover(fast=10, slow=30).generate_positions(df)
    assert pos.between(0.0, 1.0).all()
    assert (pos.iloc[:30] == 0.0).all(), "warmup period must be flat"


def test_sma_allow_short_can_emit_negative():
    df = _synthetic_ohlcv()
    pos = SMACrossover(fast=5, slow=20, allow_short=True).generate_positions(df)
    assert pos.between(-1.0, 1.0).all()


def test_rsi_positions_binary():
    df = _synthetic_ohlcv()
    pos = RSIMeanReversion().generate_positions(df)
    assert set(pos.unique()).issubset({0.0, 1.0})
