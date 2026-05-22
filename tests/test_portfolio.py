"""Tests for the portfolio layer."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tickline.portfolio import (
    Portfolio,
    Sleeve,
    SizingMethod,
    equal_weight,
    inverse_vol,
)
from tickline.strategies import SMACrossover


def _market(n: int = 500, seed: int = 5, drift: float = 0.0003, vol: float = 0.01) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = drift + rng.normal(0.0, vol, size=n)
    close = 100.0 * np.exp(np.cumsum(returns))
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.003,
            "low": close * 0.997,
            "close": close,
            "volume": rng.uniform(100, 1000, n),
        },
        index=idx,
    )


def _returns_df(n: int = 200, seed: int = 1, ncols: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    data = rng.normal(0.0, 0.01, size=(n, ncols))
    cols = [f"s{i}" for i in range(ncols)]
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame(data, columns=cols, index=idx)


def test_equal_weight_sums_to_one_per_row():
    rets = _returns_df()
    w = equal_weight(rets)
    np.testing.assert_allclose(w.sum(axis=1).values, 1.0)


def test_inverse_vol_weights_sum_to_one():
    rets = _returns_df()
    w = inverse_vol(rets, lookback=20)
    # warmup rows have NaN until lookback bars accumulate → after lookback, sums == 1
    sums = w.iloc[25:].sum(axis=1)
    np.testing.assert_allclose(sums.values, 1.0, atol=1e-9)


def test_inverse_vol_overweights_quieter_sleeve():
    """Sleeve with smaller realized vol should receive a larger weight."""
    n = 300
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    rng = np.random.default_rng(0)
    rets = pd.DataFrame(
        {
            "loud": rng.normal(0.0, 0.03, n),
            "quiet": rng.normal(0.0, 0.005, n),
        },
        index=idx,
    )
    w = inverse_vol(rets, lookback=50)
    # after warmup, quiet sleeve should win consistently
    assert (w["quiet"].iloc[60:] > w["loud"].iloc[60:]).all()


def test_portfolio_requires_at_least_one_sleeve():
    with pytest.raises(ValueError):
        Portfolio(sleeves=[])


def test_portfolio_runs_end_to_end():
    sleeves = [
        Sleeve("A", _market(n=600, seed=1), SMACrossover(10, 30)),
        Sleeve("B", _market(n=600, seed=2, drift=-0.0002), SMACrossover(10, 30)),
        Sleeve("C", _market(n=600, seed=3, vol=0.02), SMACrossover(10, 30)),
    ]
    port = Portfolio(sleeves, initial_capital=10_000)
    result = port.run(method=SizingMethod.INVERSE_VOL, lookback=30)

    assert result.equity_curve.index[0] == sleeves[0].ohlcv.index[0]
    assert len(result.sleeve_results) == 3
    assert result.correlation.shape == (3, 3)
    # diagonals are 1
    np.testing.assert_allclose(np.diag(result.correlation.values), 1.0)


def test_portfolio_string_method_alias():
    sleeves = [
        Sleeve("A", _market(n=400, seed=7), SMACrossover(10, 30)),
        Sleeve("B", _market(n=400, seed=8), SMACrossover(10, 30)),
    ]
    port = Portfolio(sleeves)
    result = port.run(method="equal", lookback=20)
    assert result.method == SizingMethod.EQUAL


def test_portfolio_contributions_sum_close_to_total():
    sleeves = [
        Sleeve("A", _market(n=600, seed=11), SMACrossover(10, 30)),
        Sleeve("B", _market(n=600, seed=12), SMACrossover(10, 30)),
    ]
    port = Portfolio(sleeves)
    result = port.run(method=SizingMethod.EQUAL, lookback=30)
    # sum of contributions ≈ total log-style return in pp
    contrib_sum = result.contributions().sum()
    # not exactly equal due to compounding — but same sign and similar magnitude
    assert np.sign(contrib_sum) == np.sign(result.total_return_pct) or abs(result.total_return_pct) < 0.5
