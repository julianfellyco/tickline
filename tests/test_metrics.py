"""Tests for performance metrics."""

from __future__ import annotations

import pandas as pd
import pytest

from tickline.risk import compute_metrics


def _series(values: list[float], freq: str = "1h") -> pd.Series:
    idx = pd.date_range("2024-01-01", periods=len(values), freq=freq, tz="UTC")
    return pd.Series(values, index=idx)


def _empty_trades() -> pd.DataFrame:
    return pd.DataFrame(columns=["entry_ts", "exit_ts", "side", "entry_px", "exit_px", "pnl_pct"])


def test_metrics_on_constant_growth():
    equity = _series([100, 101, 102, 103, 104, 105])
    returns = equity.pct_change().fillna(0.0)
    m = compute_metrics(returns, equity, _empty_trades(), "1h")
    assert m.total_return_pct > 0
    assert m.max_drawdown_pct == 0.0


def test_max_drawdown_detected():
    equity = _series([100, 110, 120, 90, 95, 100])
    returns = equity.pct_change().fillna(0.0)
    m = compute_metrics(returns, equity, _empty_trades(), "1h")
    expected_dd_pct = (90 / 120 - 1.0) * 100.0
    assert m.max_drawdown_pct == pytest.approx(expected_dd_pct, rel=1e-6)


def test_win_rate_from_trades():
    trades = pd.DataFrame(
        [
            {"entry_ts": 0, "exit_ts": 1, "side": "long", "entry_px": 100, "exit_px": 110, "pnl_pct": 0.10},
            {"entry_ts": 2, "exit_ts": 3, "side": "long", "entry_px": 100, "exit_px": 95, "pnl_pct": -0.05},
            {"entry_ts": 4, "exit_ts": 5, "side": "long", "entry_px": 100, "exit_px": 105, "pnl_pct": 0.05},
        ]
    )
    equity = _series([100, 110, 110, 105, 105, 110])
    returns = equity.pct_change().fillna(0.0)
    m = compute_metrics(returns, equity, trades, "1h")
    assert m.num_trades == 3
    assert m.win_rate_pct == pytest.approx(66.666, rel=1e-3)
    assert m.profit_factor > 1.0
