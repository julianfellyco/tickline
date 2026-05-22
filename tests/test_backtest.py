"""Tests for the backtest engine."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tickline.backtest import Backtester, CostModel
from tickline.strategies import SMACrossover
from tickline.strategies.base import Strategy


class AlwaysLong(Strategy):
    name = "always_long"

    def generate_positions(self, ohlcv: pd.DataFrame) -> pd.Series:
        return pd.Series(1.0, index=ohlcv.index, name="position")


class AlwaysFlat(Strategy):
    name = "always_flat"

    def generate_positions(self, ohlcv: pd.DataFrame) -> pd.Series:
        return pd.Series(0.0, index=ohlcv.index, name="position")


def _flat_market(n: int = 100) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    close = pd.Series(100.0, index=idx)
    return pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": 1.0}
    )


def _trending_market(n: int = 100) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    close = pd.Series(np.linspace(100, 150, n), index=idx)
    return pd.DataFrame(
        {"open": close, "high": close * 1.001, "low": close * 0.999, "close": close, "volume": 1.0}
    )


def test_always_flat_preserves_capital():
    bt = Backtester(initial_capital=10_000)
    result = bt.run(_flat_market(), AlwaysFlat())
    assert result.final_equity == pytest.approx(10_000, rel=1e-6)
    assert result.num_trades == 0


def test_always_long_in_trending_market_makes_money():
    bt = Backtester(initial_capital=10_000, cost_model=CostModel(fee_bps=0, slippage_bps=0))
    result = bt.run(_trending_market(), AlwaysLong())
    assert result.final_equity > 10_000
    assert result.total_return_pct > 40.0  # ~50% trend, allow some slop


def test_costs_reduce_returns():
    market = _trending_market()
    free = Backtester(cost_model=CostModel(fee_bps=0, slippage_bps=0)).run(market, AlwaysLong())
    paid = Backtester(cost_model=CostModel(fee_bps=50, slippage_bps=50)).run(market, AlwaysLong())
    assert paid.final_equity < free.final_equity


def test_no_lookahead_bias():
    """Position at bar t must use signal from bar t-1."""
    market = _trending_market(n=50)
    bt = Backtester()
    result = bt.run(market, SMACrossover(fast=5, slow=10))
    assert result.positions.iloc[0] == 0.0, "first bar must be flat (no signal yet)"


def test_empty_input_raises():
    bt = Backtester()
    with pytest.raises(ValueError):
        bt.run(pd.DataFrame(), AlwaysLong())
