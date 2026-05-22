"""Tests for the volatility-targeted sizing wrapper."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tickline.strategies import VolatilityTargeted
from tickline.strategies.base import Strategy


class _AlwaysLong(Strategy):
    name = "always_long"
    def generate_positions(self, ohlcv):
        return pd.Series(1.0, index=ohlcv.index)


def _market(n: int, vol: float, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    closes = 100.0 * np.exp(np.cumsum(rng.normal(0.0, vol, n)))
    idx = pd.date_range("2025-01-01", periods=n, freq="1h", tz="UTC")
    close = pd.Series(closes, index=idx)
    return pd.DataFrame({"open": close, "high": close * 1.002, "low": close * 0.998,
                         "close": close, "volume": 1.0}, index=idx)


def test_rejects_bad_params():
    with pytest.raises(ValueError):
        VolatilityTargeted(_AlwaysLong(), target_annual_vol=0)
    with pytest.raises(ValueError):
        VolatilityTargeted(_AlwaysLong(), lookback=1)
    with pytest.raises(ValueError):
        VolatilityTargeted(_AlwaysLong(), max_leverage=0)


def test_warmup_period_is_flat():
    df = _market(200, vol=0.01)
    pos = VolatilityTargeted(_AlwaysLong(), lookback=50).generate_positions(df)
    # warmup: pct_change makes bar 0 a NaN that gets filled to 0; rolling(50)
    # has enough data starting at bar 49. So the strictly-flat region is
    # bars 0..48.
    assert (pos.iloc[:49] == 0.0).all()


def test_high_vol_scales_position_down():
    """A noisier market under the same primary should get a smaller position."""
    df_calm = _market(500, vol=0.003, seed=1)
    df_wild = _market(500, vol=0.025, seed=1)
    vt = VolatilityTargeted(_AlwaysLong(), target_annual_vol=0.15, lookback=20, max_leverage=2.0)
    pos_calm = vt.generate_positions(df_calm)
    pos_wild = vt.generate_positions(df_wild)
    # average post-warmup position must be larger in calm market
    assert pos_calm.iloc[60:].mean() > pos_wild.iloc[60:].mean()


def test_leverage_cap_respected():
    df = _market(300, vol=0.001)  # near-zero vol → would push leverage huge
    pos = VolatilityTargeted(_AlwaysLong(), target_annual_vol=0.15, lookback=20, max_leverage=2.0).generate_positions(df)
    assert pos.abs().max() <= 2.0 + 1e-9


def test_zero_primary_means_zero_output():
    class _Flat(Strategy):
        name = "flat"
        def generate_positions(self, ohlcv):
            return pd.Series(0.0, index=ohlcv.index)
    df = _market(200, vol=0.01)
    pos = VolatilityTargeted(_Flat(), lookback=20).generate_positions(df)
    assert (pos == 0.0).all()
