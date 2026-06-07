"""Tests for trend timing (deterministic, no network)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tickline.timing import breadth, buy_hold, portfolio, trend_follow, trend_position


def _series(rates, start=100.0):
    """Build a price series from a list of per-bar return rates."""
    close = [start]
    for r in rates:
        close.append(close[-1] * (1 + r))
    idx = pd.date_range("2020-01-01", periods=len(close), freq="D", tz="UTC")
    return pd.Series(close, index=idx)


def _frame(close):
    return pd.DataFrame({"open": close, "high": close, "low": close,
                         "close": close, "volume": 1e6})


# --- no lookahead (the critical one) -----------------------------------------
def test_trend_position_is_point_in_time():
    close = _series(list(np.linspace(0.01, -0.01, 60)))
    pos = trend_position(close, ma_window=10)
    ma = close.rolling(10, min_periods=5).mean()
    expected = (close > ma).shift(1).fillna(False).astype(float)
    assert pos.equals(expected)
    # truncating the series must not change earlier positions
    trunc = trend_position(close.iloc[:40], ma_window=10)
    assert trunc.iloc[-1] == pytest.approx(pos.iloc[39])


def test_trend_position_in_when_above_ma():
    close = _series([0.02] * 60)  # steady uptrend -> stays above MA
    pos = trend_position(close, ma_window=20)
    assert pos.iloc[-1] == 1.0
    assert pos.mean() > 0.7


# --- metrics -----------------------------------------------------------------
def test_buy_hold_uptrend_positive_no_drawdown():
    bh = buy_hold(_series([0.01] * 300))
    assert bh.cagr > 0
    assert bh.max_dd == pytest.approx(0.0, abs=1e-9)
    assert bh.time_in == 1.0
    assert bh.switches == 0


def test_trend_follow_cuts_drawdown_on_a_crash():
    # 250 bars up, then a sharp 60-bar crash
    rates = [0.003] * 250 + [-0.025] * 60
    close = _series(rates)
    bh = buy_hold(close)
    tf = trend_follow(close, ma_window=200, cost_bps=5.0)
    # trend-follow should exit during the crash -> shallower drawdown
    assert tf.max_dd > bh.max_dd          # less negative = shallower
    assert tf.time_in < 1.0               # spent time in cash
    assert tf.switches >= 1


# --- breadth + portfolio -----------------------------------------------------
def test_breadth_is_fraction_in_range():
    frames = {"A": _frame(_series([0.01] * 80)),      # uptrend -> above MA
              "B": _frame(_series([-0.01] * 80))}     # downtrend -> below MA
    b = breadth(frames, ma_window=20).dropna()
    assert (b >= 0).all() and (b <= 1).all()
    assert b.iloc[-1] == pytest.approx(0.5)  # one up, one down


def test_portfolio_returns_two_stats():
    frames = {"A": _frame(_series([0.005] * 300)),
              "B": _frame(_series([0.002] * 300))}
    tf, bh = portfolio(frames, ma_window=100, cost_bps=5.0)
    assert tf.label.startswith("portfolio")
    assert bh.time_in == 1.0
    assert tf.cagr == tf.cagr  # not NaN
