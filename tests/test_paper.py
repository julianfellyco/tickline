"""Tests for the paper trading layer."""

from __future__ import annotations

import json
import numpy as np
import pandas as pd
import pytest

from tickline.backtest.engine import CostModel
from tickline.paper import Ledger, Order, PaperBroker, PaperRunner
from tickline.paper.broker import Side
from tickline.strategies import SMACrossover


def _market(n: int = 200, seed: int = 3, drift: float = 0.0005) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = drift + rng.normal(0.0, 0.01, n)
    close = 100.0 * np.exp(np.cumsum(returns))
    idx = pd.date_range("2025-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame(
        {"open": close, "high": close * 1.003, "low": close * 0.997, "close": close, "volume": 1.0},
        index=idx,
    )


def test_broker_buy_then_sell_realizes_pnl():
    broker = PaperBroker(initial_cash=10_000.0, cost_model=CostModel(fee_bps=0, slippage_bps=0))
    ts = pd.Timestamp("2025-01-01", tz="UTC")
    broker.submit(Order(ts=ts, symbol="BTC", side=Side.BUY, quantity=1.0), fill_price=100.0)
    assert broker.position("BTC") == pytest.approx(1.0)
    assert broker.state.cash == pytest.approx(9_900.0)

    broker.submit(Order(ts=ts, symbol="BTC", side=Side.SELL, quantity=1.0), fill_price=110.0)
    assert broker.position("BTC") == pytest.approx(0.0)
    assert broker.state.cash == pytest.approx(10_010.0)


def test_broker_rejects_buy_without_cash():
    broker = PaperBroker(initial_cash=50.0, cost_model=CostModel(fee_bps=0, slippage_bps=0))
    ts = pd.Timestamp("2025-01-01", tz="UTC")
    with pytest.raises(ValueError):
        broker.submit(Order(ts=ts, symbol="BTC", side=Side.BUY, quantity=1.0), fill_price=100.0)


def test_broker_charges_fee_on_fill():
    broker = PaperBroker(initial_cash=10_000.0, cost_model=CostModel(fee_bps=10, slippage_bps=10))
    ts = pd.Timestamp("2025-01-01", tz="UTC")
    broker.submit(Order(ts=ts, symbol="BTC", side=Side.BUY, quantity=1.0), fill_price=100.0)
    # cash = 10_000 - 100 - (100 * 0.002) = 9_899.80
    assert broker.state.cash == pytest.approx(9_899.80)


def test_reconcile_to_target_long_then_flat():
    broker = PaperBroker(initial_cash=10_000.0, cost_model=CostModel(fee_bps=0, slippage_bps=0))
    ts = pd.Timestamp("2025-01-01", tz="UTC")
    # target 1.0 = use full $10k at $100 → 100 units
    fill = broker.reconcile_to_target("BTC", 1.0, price=100.0, ts=ts, position_size_cash=10_000.0)
    assert fill is not None
    assert broker.position("BTC") == pytest.approx(100.0)
    # target 0 = flatten
    fill = broker.reconcile_to_target("BTC", 0.0, price=110.0, ts=ts, position_size_cash=10_000.0)
    assert fill is not None
    assert broker.position("BTC") == pytest.approx(0.0)


def test_paper_runner_end_to_end_makes_trades():
    df = _market(n=300, drift=0.001)
    runner = PaperRunner(
        symbol="BTC",
        strategy=SMACrossover(10, 30),
        initial_cash=10_000.0,
        cost_model=CostModel(),
    )
    result = runner.run(df)
    assert result.num_fills > 0
    assert result.equity_curve.iloc[0] == pytest.approx(10_000.0, rel=1e-4)
    assert len(result.equity_curve) == len(df)


def test_ledger_persists_fills(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger = Ledger(path)
    runner = PaperRunner(
        symbol="BTC",
        strategy=SMACrossover(10, 30),
        initial_cash=10_000.0,
        ledger_path=path,
    )
    df = _market(n=200, drift=0.001)
    result = runner.run(df)
    rows = ledger.read()
    assert len(rows) == result.num_fills
    if rows:
        assert rows[0]["symbol"] == "BTC"
        assert "price" in rows[0]
