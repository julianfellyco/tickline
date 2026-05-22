"""Paper trading runner.

Replays an OHLCV frame through a strategy, sending orders to the
PaperBroker, persisting every fill to a Ledger. Identical shape to a
live runner — only the bar source changes (cached parquet here, live
WebSocket in production).

For the live path, the strategy and broker interfaces are unchanged.
This is the seam where you would:

  1. Replace `for bar in ohlcv` with a WebSocket subscription
  2. Replace `bar.open` with the actual fill price the exchange returns
  3. Replace the in-memory Ledger with an exchange-side trade endpoint
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from ..backtest.engine import CostModel
from ..strategies.base import Strategy
from .broker import Fill, PaperBroker
from .ledger import Ledger


@dataclass
class PaperResult:
    final_equity: float
    initial_cash: float
    fills: list[Fill]
    equity_curve: pd.Series
    ledger_path: Path | None

    @property
    def total_return_pct(self) -> float:
        return (self.final_equity / self.initial_cash - 1.0) * 100.0

    @property
    def num_fills(self) -> int:
        return len(self.fills)


class PaperRunner:
    def __init__(
        self,
        symbol: str,
        strategy: Strategy,
        initial_cash: float = 10_000.0,
        cost_model: CostModel | None = None,
        ledger_path: str | Path | None = None,
        position_size_cash: float | None = None,
        cash_buffer_pct: float = 0.01,
    ):
        """`position_size_cash` is the cash budget the strategy is allowed to
        deploy. Defaults to `initial_cash * (1 - cash_buffer_pct)` so fees
        never bounce a fill at full deployment."""
        self.symbol = symbol
        self.strategy = strategy
        self.broker = PaperBroker(initial_cash=initial_cash, cost_model=cost_model)
        self.ledger: Ledger | None = Ledger(ledger_path) if ledger_path else None
        if position_size_cash is None:
            position_size_cash = initial_cash * (1 - cash_buffer_pct)
        self.position_size_cash = position_size_cash

    def run(self, ohlcv: pd.DataFrame) -> PaperResult:
        if ohlcv.empty:
            raise ValueError("ohlcv is empty")

        # generate full position series once (vectorized) — values in [-1, 1]
        positions = self.strategy.generate_positions(ohlcv).fillna(0.0).clip(-1.0, 1.0)

        equity_at_bar = []
        last_target = 0.0
        for i in range(len(ohlcv)):
            ts = ohlcv.index[i]
            signal = float(positions.iloc[i - 1]) if i > 0 else 0.0
            fill_price = float(ohlcv["open"].iloc[i])
            self.broker.mark(self.symbol, fill_price)

            # event-driven: only act when target *changes* (open or close a position)
            if signal != last_target:
                from .broker import Order, Side
                # close existing position first if any
                current_qty = self.broker.position(self.symbol)
                if abs(current_qty) > 1e-12:
                    close_side = Side.SELL if current_qty > 0 else Side.BUY
                    fill = self.broker.submit(
                        Order(ts=ts, symbol=self.symbol, side=close_side, quantity=abs(current_qty), note="close"),
                        fill_price=fill_price,
                    )
                    if self.ledger is not None:
                        self.ledger.append(fill)

                # open new position sized off current cash
                if abs(signal) > 1e-12:
                    deployable = self.broker.state.cash * (1.0 - 2 * self.broker.cost_model.total_per_trade)
                    qty = abs(signal) * deployable / fill_price
                    side = Side.BUY if signal > 0 else Side.SELL
                    if qty > 1e-12 and (side == Side.SELL or qty * fill_price * (1 + self.broker.cost_model.total_per_trade) <= self.broker.state.cash):
                        fill = self.broker.submit(
                            Order(ts=ts, symbol=self.symbol, side=side, quantity=qty, note="open"),
                            fill_price=fill_price,
                        )
                        if self.ledger is not None:
                            self.ledger.append(fill)
                last_target = signal

            # mark to close so equity reflects intra-bar PnL
            self.broker.mark(self.symbol, float(ohlcv["close"].iloc[i]))
            equity_at_bar.append(self.broker.equity())

        equity_curve = pd.Series(equity_at_bar, index=ohlcv.index, name="equity")
        return PaperResult(
            final_equity=self.broker.equity(),
            initial_cash=self.broker.initial_cash,
            fills=list(self.broker.fills),
            equity_curve=equity_curve,
            ledger_path=self.ledger.path if self.ledger else None,
        )
