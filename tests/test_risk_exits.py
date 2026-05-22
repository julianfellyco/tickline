"""Tests for the ATR stop-loss / take-profit wrapper."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tickline.strategies import SMACrossover, StopAndTarget, atr
from tickline.strategies.base import Strategy


class _AlwaysLong(Strategy):
    name = "always_long"
    def generate_positions(self, ohlcv):
        return pd.Series(1.0, index=ohlcv.index)


class _AlwaysFlat(Strategy):
    name = "flat"
    def generate_positions(self, ohlcv):
        return pd.Series(0.0, index=ohlcv.index)


def _bars_from_close(closes: list[float], spread_pct: float = 0.005) -> pd.DataFrame:
    """Build OHLCV from a close series with a fixed-width high/low band."""
    idx = pd.date_range("2025-01-01", periods=len(closes), freq="1h", tz="UTC")
    close = pd.Series(closes, index=idx)
    high = close * (1 + spread_pct)
    low = close * (1 - spread_pct)
    return pd.DataFrame({"open": close, "high": high, "low": low, "close": close, "volume": 1.0}, index=idx)


def test_atr_is_positive_after_warmup():
    df = _bars_from_close([100.0 + i * 0.1 for i in range(50)])
    a = atr(df, period=14)
    assert (a.iloc[14:] > 0).all()


def test_atr_is_causal_no_lookahead():
    df = _bars_from_close([100.0 + np.sin(i / 5) for i in range(60)])
    a1 = atr(df, period=14)
    # truncating future data must not change the early ATR values
    a2 = atr(df.iloc[:30], period=14)
    np.testing.assert_allclose(a1.iloc[:30].values, a2.values, rtol=1e-9)


def test_wrapper_rejects_bad_params():
    with pytest.raises(ValueError):
        StopAndTarget(_AlwaysLong(), stop_atr=0)
    with pytest.raises(ValueError):
        StopAndTarget(_AlwaysLong(), target_atr=-1)
    with pytest.raises(ValueError):
        StopAndTarget(_AlwaysLong(), atr_window=1)


def test_wrapper_does_nothing_with_flat_primary():
    df = _bars_from_close([100.0 + i for i in range(50)])
    pos = StopAndTarget(_AlwaysFlat()).generate_positions(df)
    assert (pos == 0.0).all()


def test_stop_loss_triggers_on_adverse_move():
    # gentle rise then sharp drop — stop should fire
    closes = [100.0] * 30 + [100.0 - i * 1.5 for i in range(20)]  # crash from 100 → 70
    df = _bars_from_close(closes, spread_pct=0.001)
    primary = _AlwaysLong()
    wrapped = StopAndTarget(primary, stop_atr=2.0, target_atr=10.0, atr_window=14)
    pos = wrapped.generate_positions(df)
    # by the end of the crash, position must be 0 (stop fired)
    assert pos.iloc[-1] == 0.0
    # primary stays long the whole time
    assert (primary.generate_positions(df) == 1.0).all()


def test_take_profit_triggers_on_favorable_move():
    closes = [100.0] * 30 + [100.0 + i * 2.0 for i in range(20)]  # rally 100 → 140
    df = _bars_from_close(closes, spread_pct=0.001)
    wrapped = StopAndTarget(_AlwaysLong(), stop_atr=10.0, target_atr=2.0, atr_window=14)
    pos = wrapped.generate_positions(df)
    # somewhere during the rally, the target must fire
    assert (pos == 0.0).any()


def test_wrapper_re_arms_only_after_primary_goes_flat():
    """After a forced exit, we should NOT instantly re-enter on the same signal."""
    closes = [100.0] * 30 + [100.0 - i * 1.5 for i in range(15)] + [100.0] * 10
    df = _bars_from_close(closes, spread_pct=0.001)
    wrapped = StopAndTarget(_AlwaysLong(), stop_atr=2.0, target_atr=10.0, atr_window=14)
    pos = wrapped.generate_positions(df)
    # primary never goes flat → after stop, must stay flat for the rest of the run
    assert pos.iloc[-1] == 0.0


def test_wrapper_compatible_with_sma_strategy():
    """End-to-end smoke: composing with a real strategy doesn't crash."""
    rng = np.random.default_rng(7)
    closes = 100.0 * np.exp(np.cumsum(rng.normal(0.0005, 0.01, 400)))
    df = _bars_from_close(list(closes))
    wrapped = StopAndTarget(SMACrossover(20, 50), stop_atr=2.0, target_atr=3.0)
    pos = wrapped.generate_positions(df)
    assert len(pos) == len(df)
    assert pos.between(-1.0, 1.0).all()
