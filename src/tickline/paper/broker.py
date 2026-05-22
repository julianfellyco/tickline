"""Paper broker — a virtual execution venue.

The broker is *not* a backtester. The backtester runs over historical
data in bulk; the broker accepts one order at a time and pays the same
costs a real exchange would charge. This is the seam where live
trading plugs in — replace the broker, keep the strategy.

State is in-memory; the runner persists trades to disk via the Ledger.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

import pandas as pd

from ..backtest.engine import CostModel


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True)
class Order:
    ts: pd.Timestamp
    symbol: str
    side: Side
    quantity: float          # base asset units; sign is implied by side
    type: str = "market"     # 'market' for v1
    note: str = ""


@dataclass(frozen=True)
class Fill:
    order_ts: pd.Timestamp
    fill_ts: pd.Timestamp
    symbol: str
    side: Side
    quantity: float
    price: float
    cost: float              # $ in fees/slippage charged
    cash_after: float
    position_after: float


@dataclass
class BrokerState:
    cash: float
    positions: dict[str, float] = field(default_factory=dict)
    last_price: dict[str, float] = field(default_factory=dict)

    def equity(self) -> float:
        mark_to_market = sum(
            qty * self.last_price.get(symbol, 0.0)
            for symbol, qty in self.positions.items()
        )
        return self.cash + mark_to_market


class PaperBroker:
    """Single-symbol-per-call broker with realistic execution costs."""

    def __init__(
        self,
        initial_cash: float = 10_000.0,
        cost_model: CostModel | None = None,
    ):
        self.initial_cash = initial_cash
        self.cost_model = cost_model or CostModel()
        self.state = BrokerState(cash=initial_cash)
        self.fills: list[Fill] = []

    def mark(self, symbol: str, price: float) -> None:
        """Update most recent price used for equity mark and fills."""
        self.state.last_price[symbol] = price

    def submit(self, order: Order, fill_price: float) -> Fill:
        """Execute a market order at `fill_price`. Slippage + fees deducted."""
        if order.quantity <= 0:
            raise ValueError("quantity must be > 0; use Side to express direction")

        notional = order.quantity * fill_price
        cost = notional * self.cost_model.total_per_trade
        signed_qty = order.quantity if order.side == Side.BUY else -order.quantity
        cash_delta = -notional if order.side == Side.BUY else +notional

        new_cash = self.state.cash + cash_delta - cost
        if order.side == Side.BUY and new_cash < 0:
            raise ValueError(f"insufficient cash: need {notional + cost:.2f}, have {self.state.cash:.2f}")

        self.state.cash = new_cash
        self.state.positions[order.symbol] = (
            self.state.positions.get(order.symbol, 0.0) + signed_qty
        )
        self.state.last_price[order.symbol] = fill_price

        fill = Fill(
            order_ts=order.ts,
            fill_ts=pd.Timestamp(datetime.now(tz=timezone.utc)),
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=fill_price,
            cost=cost,
            cash_after=self.state.cash,
            position_after=self.state.positions[order.symbol],
        )
        self.fills.append(fill)
        return fill

    def position(self, symbol: str) -> float:
        return self.state.positions.get(symbol, 0.0)

    def equity(self) -> float:
        return self.state.equity()

    def reconcile_to_target(
        self,
        symbol: str,
        target_position: float,
        price: float,
        ts: pd.Timestamp,
        position_size_cash: float | None = None,
    ) -> Fill | None:
        """Bring current position to `target_position` (in units of base asset).

        If `position_size_cash` is provided, target is interpreted as fraction
        of *that* cash to deploy (target ∈ [-1, 1] → quantity in base units).
        Otherwise target is taken as base-asset quantity directly.
        """
        if position_size_cash is not None:
            target_qty = (target_position * position_size_cash) / price
        else:
            target_qty = target_position

        current = self.position(symbol)
        delta = target_qty - current
        if abs(delta) < 1e-12:
            return None
        side = Side.BUY if delta > 0 else Side.SELL
        order = Order(ts=ts, symbol=symbol, side=side, quantity=abs(delta), note="reconcile")
        return self.submit(order, fill_price=price)
