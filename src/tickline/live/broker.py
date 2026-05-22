"""Live broker — ccxt-backed market data + (optionally) order placement.

Modes, in order of safety:

  1. shadow + sandbox (default)
       Reads real market data from the exchange's sandbox/testnet.
       Simulates fills locally with the same cost model the backtester
       uses. No real orders. Safe to run unattended.

  2. shadow=false + sandbox=true
       Places real orders on the exchange's testnet using test funds.
       Requires testnet API keys (free, but exchange-specific). No real
       money at risk.

  3. shadow=false + sandbox=false
       Places real orders on the live exchange with real money.
       Requires real API keys. **Three deliberate steps from default.**

The same interface (`mark`, `submit`, `position`, `equity`) is used in
all three modes — the strategy + runner code does not change.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import ccxt
import pandas as pd

from ..backtest.engine import CostModel
from ..paper.broker import Fill, Order, Side
from .config import LiveConfig


class LiveBroker:
    def __init__(
        self,
        config: LiveConfig | None = None,
        cost_model: CostModel | None = None,
        initial_cash: float = 10_000.0,
        exchange_factory: Any = None,
    ):
        self.config = config or LiveConfig.from_env()
        self.cost_model = cost_model or CostModel()
        self.initial_cash = initial_cash

        # in shadow mode we keep a local virtual book
        self._shadow_cash = initial_cash
        self._shadow_positions: dict[str, float] = {}
        self._last_price: dict[str, float] = {}
        self.fills: list[Fill] = []

        if exchange_factory is None:
            cls = getattr(ccxt, self.config.exchange)
            kwargs: dict[str, Any] = {"enableRateLimit": True}
            if self.config.api_key and self.config.secret:
                kwargs["apiKey"] = self.config.api_key
                kwargs["secret"] = self.config.secret
            self.exchange = cls(kwargs)
            if self.config.sandbox:
                try:
                    self.exchange.set_sandbox_mode(True)
                except Exception:
                    pass
        else:
            # injected mock for tests
            self.exchange = exchange_factory

    # ─── market data ──────────────────────────────────────────────

    def fetch_history(self, symbol: str, timeframe: str, limit: int = 200) -> pd.DataFrame:
        """Fetch the most recent `limit` OHLCV bars from the exchange."""
        candles = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        if not candles:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        df = pd.DataFrame(candles, columns=["ts", "open", "high", "low", "close", "volume"])
        df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
        df = df.set_index("ts")
        if not df.empty:
            self._last_price[symbol] = float(df["close"].iloc[-1])
        return df

    def fetch_ticker_price(self, symbol: str) -> float:
        ticker = self.exchange.fetch_ticker(symbol)
        price = float(ticker["last"])
        self._last_price[symbol] = price
        return price

    # ─── account ──────────────────────────────────────────────────

    def mark(self, symbol: str, price: float) -> None:
        self._last_price[symbol] = price

    def position(self, symbol: str) -> float:
        if self.config.can_place_real_orders:
            try:
                base = symbol.split("/")[0]
                balance = self.exchange.fetch_balance()
                return float(balance.get(base, {}).get("free", 0.0))
            except Exception:
                pass
        return self._shadow_positions.get(symbol, 0.0)

    def equity(self) -> float:
        if self.config.can_place_real_orders:
            try:
                total = self.exchange.fetch_balance().get("total", {})
                if isinstance(total, dict):
                    return float(sum(v for v in total.values() if isinstance(v, (int, float))))
            except Exception:
                pass
        mtm = sum(
            qty * self._last_price.get(symbol, 0.0)
            for symbol, qty in self._shadow_positions.items()
        )
        return self._shadow_cash + mtm

    # ─── execution ────────────────────────────────────────────────

    def submit(self, order: Order, current_price: float | None = None) -> Fill:
        if order.quantity <= 0:
            raise ValueError("quantity must be > 0")

        if self.config.can_place_real_orders:
            return self._submit_real(order)
        return self._submit_shadow(order, current_price)

    def _submit_shadow(self, order: Order, current_price: float | None) -> Fill:
        price = current_price if current_price is not None else self._last_price.get(order.symbol)
        if price is None or price <= 0:
            raise ValueError(f"no price for {order.symbol}; call mark() or fetch first")
        notional = order.quantity * price
        cost = notional * self.cost_model.total_per_trade
        signed = order.quantity if order.side == Side.BUY else -order.quantity
        cash_delta = -notional if order.side == Side.BUY else +notional

        new_cash = self._shadow_cash + cash_delta - cost
        if order.side == Side.BUY and new_cash < 0:
            raise ValueError(
                f"insufficient shadow cash: need {notional + cost:.2f}, have {self._shadow_cash:.2f}"
            )
        self._shadow_cash = new_cash
        self._shadow_positions[order.symbol] = self._shadow_positions.get(order.symbol, 0.0) + signed
        self._last_price[order.symbol] = price
        fill = Fill(
            order_ts=order.ts,
            fill_ts=pd.Timestamp(datetime.now(tz=timezone.utc)),
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=price,
            cost=cost,
            cash_after=self._shadow_cash,
            position_after=self._shadow_positions[order.symbol],
        )
        self.fills.append(fill)
        return fill

    def _submit_real(self, order: Order) -> Fill:
        side_str = "buy" if order.side == Side.BUY else "sell"
        result = self.exchange.create_market_order(order.symbol, side_str, order.quantity)
        price = float(result.get("average") or result.get("price") or self._last_price.get(order.symbol, 0.0))
        notional = order.quantity * price
        cost = float(result.get("fee", {}).get("cost", notional * self.cost_model.fee_bps / 10_000))
        fill = Fill(
            order_ts=order.ts,
            fill_ts=pd.Timestamp(datetime.now(tz=timezone.utc)),
            symbol=order.symbol,
            side=order.side,
            quantity=float(result.get("filled", order.quantity)),
            price=price,
            cost=cost,
            cash_after=self.equity(),
            position_after=self.position(order.symbol),
        )
        self.fills.append(fill)
        return fill
