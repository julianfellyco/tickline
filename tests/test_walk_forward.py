"""Tests for walk-forward validation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tickline.backtest import run_walk_forward
from tickline.strategies import SMACrossover


def _synthetic(n: int = 3000, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.0002, 0.01, size=n)
    close = 100.0 * np.exp(np.cumsum(returns))
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.003,
            "low": close * 0.997,
            "close": close,
            "volume": rng.uniform(100, 1000, size=n),
        },
        index=idx,
    )


def test_walk_forward_produces_expected_number_of_windows():
    df = _synthetic(3000)
    result = run_walk_forward(
        df,
        strategy_factory=lambda: SMACrossover(20, 50),
        train_bars=1000,
        test_bars=500,
        mode="anchored",
    )
    # after first 1000 train bars, 2000 remain → 4 test windows of 500
    assert len(result.windows) == 4


def test_rolling_mode_has_constant_train_size():
    df = _synthetic(3000)
    result = run_walk_forward(
        df,
        strategy_factory=lambda: SMACrossover(20, 50),
        train_bars=1000,
        test_bars=500,
        mode="rolling",
    )
    sizes = {
        (w.train_end - w.train_start).total_seconds() / 3600 for w in result.windows
    }
    # all train windows span the same time (within 1h tolerance for index width)
    assert len(sizes) == 1


def test_walk_forward_rejects_bad_mode():
    df = _synthetic(2000)
    with pytest.raises(ValueError):
        run_walk_forward(
            df,
            strategy_factory=lambda: SMACrossover(20, 50),
            train_bars=500,
            test_bars=200,
            mode="bogus",
        )


def test_walk_forward_rejects_insufficient_data():
    df = _synthetic(200)
    with pytest.raises(ValueError):
        run_walk_forward(
            df,
            strategy_factory=lambda: SMACrossover(20, 50),
            train_bars=1000,
            test_bars=500,
        )


def test_summary_dataframe_shape():
    df = _synthetic(3000)
    result = run_walk_forward(
        df,
        strategy_factory=lambda: SMACrossover(20, 50),
        train_bars=1000,
        test_bars=500,
    )
    summary = result.summary()
    assert {"window", "test_start", "test_end", "return_pct", "sharpe"} <= set(summary.columns)
    assert len(summary) == len(result.windows)


def test_consistency_in_unit_range():
    df = _synthetic(3000)
    result = run_walk_forward(
        df,
        strategy_factory=lambda: SMACrossover(20, 50),
        train_bars=1000,
        test_bars=500,
    )
    c = result.sharpe_consistency()
    assert 0.0 <= c <= 1.0
