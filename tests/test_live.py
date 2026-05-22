"""Tests for the live trading layer.

Uses a fake exchange so no network calls happen during tests.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tickline.backtest.engine import CostModel
from tickline.live import LiveBroker, LiveConfig, LiveRunner
from tickline.paper.broker import Order, Side
from tickline.strategies.base import Strategy


class _FakeExchange:
    """Deterministic fake matching the ccxt surface we use."""

    def __init__(self, candles: list[list[float]]):
        self.candles = candles
        self.calls: list[str] = []

    def fetch_ohlcv(self, symbol, timeframe, limit=None):
        self.calls.append(f"fetch_ohlcv:{symbol}:{timeframe}:{limit}")
        return list(self.candles[-(limit or len(self.candles)):])

    def fetch_ticker(self, symbol):
        self.calls.append(f"fetch_ticker:{symbol}")
        return {"last": self.candles[-1][4]}

    def set_sandbox_mode(self, on):
        self.calls.append(f"set_sandbox_mode:{on}")


class _AlwaysLongAfterWarmup(Strategy):
    name = "always_long_after_warmup"
    def generate_positions(self, ohlcv):
        positions = pd.Series(1.0, index=ohlcv.index, name="position")
        # warmup: flat for first 5 bars to simulate a regular indicator
        positions.iloc[:5] = 0.0
        return positions


class _AlwaysFlat(Strategy):
    name = "flat"
    def generate_positions(self, ohlcv):
        return pd.Series(0.0, index=ohlcv.index, name="position")


def _gen_candles(n: int = 20, start_price: float = 100.0) -> list[list[float]]:
    rng = np.random.default_rng(5)
    closes = start_price * np.exp(np.cumsum(rng.normal(0.001, 0.005, n)))
    ts_ms = int(pd.Timestamp("2025-01-01", tz="UTC").timestamp() * 1000)
    out = []
    for i, c in enumerate(closes):
        out.append([
            ts_ms + i * 3_600_000,
            float(c) * 0.999, float(c) * 1.002, float(c) * 0.998, float(c),
            1000.0,
        ])
    return out


def test_config_defaults_safe():
    cfg = LiveConfig()
    assert cfg.sandbox is True
    assert cfg.shadow is True
    assert not cfg.can_place_real_orders


def test_config_requires_keys_to_place_real():
    cfg = LiveConfig(shadow=False)
    assert not cfg.can_place_real_orders
    cfg2 = LiveConfig(shadow=False, api_key="x", secret="y")
    assert cfg2.can_place_real_orders


def test_broker_shadow_buy_then_sell():
    fake = _FakeExchange(_gen_candles(10))
    broker = LiveBroker(config=LiveConfig(), cost_model=CostModel(fee_bps=0, slippage_bps=0),
                        initial_cash=10_000, exchange_factory=fake)
    ts = pd.Timestamp("2025-01-01", tz="UTC")
    broker.mark("BTC/USDT", 100.0)
    broker.submit(Order(ts=ts, symbol="BTC/USDT", side=Side.BUY, quantity=1.0), current_price=100.0)
    assert broker.position("BTC/USDT") == pytest.approx(1.0)
    broker.submit(Order(ts=ts, symbol="BTC/USDT", side=Side.SELL, quantity=1.0), current_price=110.0)
    assert broker.position("BTC/USDT") == pytest.approx(0.0)
    # PnL = +10 in shadow cash
    assert broker.equity() == pytest.approx(10_010.0)


def test_broker_rejects_oversized_buy_in_shadow():
    fake = _FakeExchange(_gen_candles(5))
    broker = LiveBroker(config=LiveConfig(), exchange_factory=fake, initial_cash=50.0)
    ts = pd.Timestamp("2025-01-01", tz="UTC")
    with pytest.raises(ValueError):
        broker.submit(Order(ts=ts, symbol="BTC/USDT", side=Side.BUY, quantity=1.0), current_price=100.0)


def test_runner_step_once_with_flat_signal():
    fake = _FakeExchange(_gen_candles(10))
    broker = LiveBroker(config=LiveConfig(), exchange_factory=fake)
    runner = LiveRunner(broker=broker, strategy=_AlwaysFlat(),
                        symbol="BTC/USDT", timeframe="1h", history_bars=10)
    step = runner.step_once()
    assert step.action == "hold"
    assert step.target_position == 0.0


def test_runner_step_once_opens_long_on_signal_change():
    fake = _FakeExchange(_gen_candles(15))
    broker = LiveBroker(config=LiveConfig(), exchange_factory=fake, initial_cash=10_000)
    runner = LiveRunner(broker=broker, strategy=_AlwaysLongAfterWarmup(),
                        symbol="BTC/USDT", timeframe="1h", history_bars=15)
    step = runner.step_once()
    # signal at second-to-last bar must be 1.0 (post-warmup), so action is open_long
    assert step.target_position == 1.0
    assert step.action == "open_long"
    assert broker.position("BTC/USDT") > 0


def test_runner_second_step_is_hold_when_signal_unchanged():
    fake = _FakeExchange(_gen_candles(20))
    broker = LiveBroker(config=LiveConfig(), exchange_factory=fake, initial_cash=10_000)
    runner = LiveRunner(broker=broker, strategy=_AlwaysLongAfterWarmup(),
                        symbol="BTC/USDT", timeframe="1h", history_bars=20)
    runner.step_once()
    second = runner.step_once()
    assert second.action == "hold"


def test_runner_ledger_persistence(tmp_path):
    ledger_path = tmp_path / "live.jsonl"
    fake = _FakeExchange(_gen_candles(15))
    broker = LiveBroker(config=LiveConfig(), exchange_factory=fake, initial_cash=10_000)
    runner = LiveRunner(broker=broker, strategy=_AlwaysLongAfterWarmup(),
                        symbol="BTC/USDT", timeframe="1h", history_bars=15, ledger_path=ledger_path)
    runner.step_once()
    rows = ledger_path.read_text().splitlines()
    assert len(rows) >= 1
