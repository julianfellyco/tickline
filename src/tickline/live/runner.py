"""Live runner — polls bars, runs strategy, sends orders.

Stateless per step: each iteration fetches a fresh history window,
generates positions on the whole window, and acts on the most recent
*closed* bar's signal. This is robust to crashes and restarts: nothing
is stored between steps that can't be recomputed from market data.

Two modes of execution:

  step_once()  ← single iteration; the entire test harness uses this
  run_loop()   ← continuous polling; one step every `interval_seconds`

`run_loop` is intentionally simple — no asyncio, no event loops, no
background threads. A real production system would replace this with
WebSocket subscriptions; the loop here keeps the demo readable.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from ..paper.broker import Order, Side
from ..paper.ledger import Ledger
from ..strategies.base import Strategy
from .broker import LiveBroker


@dataclass
class LiveStep:
    ts: pd.Timestamp
    symbol: str
    target_position: float
    current_position: float
    action: str               # 'hold' | 'open_long' | 'open_short' | 'close'
    fill_price: float | None = None
    fill_qty: float | None = None
    fill_cost: float | None = None
    note: str = ""


@dataclass
class LiveRunResult:
    steps: list[LiveStep] = field(default_factory=list)
    final_equity: float = 0.0

    @property
    def num_actions(self) -> int:
        return sum(1 for s in self.steps if s.action != "hold")


class LiveRunner:
    def __init__(
        self,
        broker: LiveBroker,
        strategy: Strategy,
        symbol: str,
        timeframe: str = "1h",
        history_bars: int = 200,
        ledger_path: str | Path | None = None,
        position_size_cash: float | None = None,
        cash_buffer_pct: float = 0.01,
    ):
        self.broker = broker
        self.strategy = strategy
        self.symbol = symbol
        self.timeframe = timeframe
        self.history_bars = history_bars
        self.ledger: Ledger | None = Ledger(ledger_path) if ledger_path else None
        if position_size_cash is None:
            position_size_cash = broker.initial_cash * (1 - cash_buffer_pct)
        self.position_size_cash = position_size_cash
        self._last_target: float = 0.0

    def step_once(self) -> LiveStep:
        """One iteration: fetch → signal → reconcile if needed."""
        history = self.broker.fetch_history(self.symbol, self.timeframe, self.history_bars)
        if history.empty or len(history) < 2:
            return LiveStep(
                ts=pd.Timestamp.now(tz="UTC"),
                symbol=self.symbol,
                target_position=0.0,
                current_position=self.broker.position(self.symbol),
                action="hold",
                note="not enough data",
            )

        positions = self.strategy.generate_positions(history).fillna(0.0).clip(-1.0, 1.0)
        # last closed bar's signal — never use the in-progress bar
        target = float(positions.iloc[-2])
        current_qty = self.broker.position(self.symbol)
        current_price = float(history["close"].iloc[-1])
        self.broker.mark(self.symbol, current_price)
        now = history.index[-1]

        if target == self._last_target:
            return LiveStep(
                ts=now, symbol=self.symbol, target_position=target,
                current_position=current_qty, action="hold", fill_price=current_price,
            )

        # event-driven: close existing position, optionally open new
        if abs(current_qty) > 1e-12:
            close_side = Side.SELL if current_qty > 0 else Side.BUY
            fill = self.broker.submit(
                Order(ts=now, symbol=self.symbol, side=close_side, quantity=abs(current_qty), note="live_close"),
                current_price=current_price,
            )
            if self.ledger is not None:
                self.ledger.append(fill)

        action = "hold"
        fill_price = fill_qty = fill_cost = None
        if abs(target) > 1e-12:
            deployable = self.position_size_cash * (1.0 - 2 * self.broker.cost_model.total_per_trade)
            qty = abs(target) * deployable / current_price
            side = Side.BUY if target > 0 else Side.SELL
            try:
                fill = self.broker.submit(
                    Order(ts=now, symbol=self.symbol, side=side, quantity=qty, note="live_open"),
                    current_price=current_price,
                )
                if self.ledger is not None:
                    self.ledger.append(fill)
                action = "open_long" if target > 0 else "open_short"
                fill_price = fill.price
                fill_qty = fill.quantity
                fill_cost = fill.cost
            except ValueError as exc:
                action = "close"
                fill_price = current_price
                # reported as note for diagnostics
                self._last_target = target
                return LiveStep(
                    ts=now, symbol=self.symbol, target_position=target,
                    current_position=self.broker.position(self.symbol), action=action,
                    fill_price=fill_price, note=f"open skipped: {exc!s}",
                )
        else:
            action = "close"
            fill_price = current_price

        self._last_target = target
        return LiveStep(
            ts=now, symbol=self.symbol, target_position=target,
            current_position=self.broker.position(self.symbol),
            action=action, fill_price=fill_price,
            fill_qty=fill_qty, fill_cost=fill_cost,
        )

    def run_loop(self, interval_seconds: int = 60, max_steps: int = 10) -> LiveRunResult:
        """Continuous polling. Sleeps `interval_seconds` between iterations."""
        result = LiveRunResult()
        for i in range(max_steps):
            step = self.step_once()
            result.steps.append(step)
            if i < max_steps - 1:
                time.sleep(interval_seconds)
        result.final_equity = self.broker.equity()
        return result
