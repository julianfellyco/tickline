"""Tests for the higher-timeframe trend filter."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tickline.strategies import HigherTimeframeFilter, SMACrossover
from tickline.strategies.base import Strategy
from tickline.strategies.trend_filter import _htf_aggregate


class _AlwaysLong(Strategy):
    name = "always_long"
    def generate_positions(self, ohlcv):
        return pd.Series(1.0, index=ohlcv.index)


class _AlwaysShort(Strategy):
    name = "always_short"
    def generate_positions(self, ohlcv):
        return pd.Series(-1.0, index=ohlcv.index)


def _market_from_closes(closes: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=len(closes), freq="1h", tz="UTC")
    close = pd.Series(closes, index=idx)
    return pd.DataFrame({
        "open": close, "high": close * 1.002, "low": close * 0.998,
        "close": close, "volume": 1.0,
    }, index=idx)


def test_htf_aggregate_drops_trailing_partial_group():
    df = _market_from_closes([100 + i for i in range(13)])
    htf = _htf_aggregate(df, multiplier=4)
    assert len(htf) == 3  # 13 // 4 = 3 complete groups
    # check OHLC of first group: bars 0..3
    assert htf["open"].iloc[0] == 100.0
    assert htf["close"].iloc[0] == 103.0
    assert htf["high"].iloc[0] >= 103.0


def test_htf_aggregate_handles_empty_when_too_short():
    df = _market_from_closes([100.0, 101.0])
    htf = _htf_aggregate(df, multiplier=4)
    assert htf.empty


def test_filter_rejects_bad_params():
    with pytest.raises(ValueError):
        HigherTimeframeFilter(_AlwaysLong(), multiplier=1)
    with pytest.raises(ValueError):
        HigherTimeframeFilter(_AlwaysLong(), sma_period=1)
    with pytest.raises(ValueError):
        HigherTimeframeFilter(_AlwaysLong(), mode="bogus")


def test_filter_blocks_long_in_strong_downtrend():
    """Always-long primary should be killed in a sustained downtrend."""
    df = _market_from_closes([100.0 - i * 0.5 for i in range(500)])
    wrapped = HigherTimeframeFilter(_AlwaysLong(), multiplier=4, sma_period=10)
    pos = wrapped.generate_positions(df)
    # majority of mature bars (post-warmup) should be flat
    mature = pos.iloc[200:]
    assert (mature == 0.0).mean() > 0.9


def test_filter_allows_long_in_strong_uptrend():
    df = _market_from_closes([100.0 + i * 0.5 for i in range(500)])
    wrapped = HigherTimeframeFilter(_AlwaysLong(), multiplier=4, sma_period=10)
    pos = wrapped.generate_positions(df)
    mature = pos.iloc[200:]
    # at least 70% of mature bars should be long
    assert (mature > 0).mean() > 0.7


def test_filter_blocks_short_in_uptrend_strict_mode():
    df = _market_from_closes([100.0 + i * 0.5 for i in range(500)])
    wrapped = HigherTimeframeFilter(_AlwaysShort(), multiplier=4, sma_period=10, mode="strict")
    pos = wrapped.generate_positions(df)
    mature = pos.iloc[200:]
    assert (mature == 0.0).mean() > 0.9


def test_long_only_mode_drops_all_shorts():
    df = _market_from_closes([100.0 + i * 0.3 for i in range(500)])
    wrapped = HigherTimeframeFilter(_AlwaysShort(), multiplier=4, sma_period=10, mode="long-only")
    pos = wrapped.generate_positions(df)
    assert (pos == 0.0).all()


def test_filter_compatible_with_sma_strategy():
    rng = np.random.default_rng(11)
    closes = 100.0 * np.exp(np.cumsum(rng.normal(0.0005, 0.01, 600)))
    df = _market_from_closes(list(closes))
    wrapped = HigherTimeframeFilter(SMACrossover(20, 50), multiplier=4, sma_period=50)
    pos = wrapped.generate_positions(df)
    assert len(pos) == len(df)
    assert pos.between(-1.0, 1.0).all()


def test_filter_returns_flat_when_insufficient_htf_history():
    df = _market_from_closes([100.0 + i for i in range(30)])
    wrapped = HigherTimeframeFilter(_AlwaysLong(), multiplier=4, sma_period=50)
    pos = wrapped.generate_positions(df)
    assert (pos == 0.0).all()


def test_filter_no_lookahead():
    """Truncating future data must not change earlier filtered positions."""
    rng = np.random.default_rng(3)
    closes = 100.0 * np.exp(np.cumsum(rng.normal(0.0005, 0.01, 400)))
    df = _market_from_closes(list(closes))
    wrapped = HigherTimeframeFilter(_AlwaysLong(), multiplier=4, sma_period=20)
    pos_full = wrapped.generate_positions(df)
    pos_partial = wrapped.generate_positions(df.iloc[:200])
    # first 200 bars must match
    np.testing.assert_allclose(pos_full.iloc[:200].values, pos_partial.values, rtol=1e-9)
