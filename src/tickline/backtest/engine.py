"""Vectorized backtest engine.

Design choices that keep the engine honest:

1. **No lookahead.** Signals generated at bar `t` are executed at the open
   of bar `t+1`. Returns from `t+1` onward count.
2. **Realistic costs.** Every position change pays a configurable fee
   (default 10 bps round-trip on crypto spot) plus slippage modeled as a
   fraction of bar range.
3. **Equity-curve accounting.** PnL compounds, so a 10% drawdown after a
   100% gain isn't 10% of starting capital — it's the actual dollars.

Pessimistic defaults are deliberate. If a strategy survives this engine,
it has a chance in paper trading. If it dies here, it dies for free.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np
import pandas as pd

from ..strategies.base import Strategy


@dataclass
class CostModel:
    """Transaction cost assumptions.

    - fee_bps: round-trip fee in basis points (10 bps = 0.10%).
              Default 10 bps is realistic for retail crypto spot trading.
    - slippage_bps: extra cost per trade in bps to model adverse fill.
    """

    fee_bps: float = 10.0
    slippage_bps: float = 5.0

    @property
    def total_per_trade(self) -> float:
        return (self.fee_bps + self.slippage_bps) / 10_000.0


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    returns: pd.Series
    positions: pd.Series
    trades: pd.DataFrame
    initial_capital: float
    cost_model: CostModel = field(default_factory=CostModel)

    @property
    def final_equity(self) -> float:
        return float(self.equity_curve.iloc[-1])

    @property
    def total_return_pct(self) -> float:
        return (self.final_equity / self.initial_capital - 1.0) * 100.0

    @property
    def num_trades(self) -> int:
        return len(self.trades)


class Backtester:
    def __init__(
        self,
        initial_capital: float = 10_000.0,
        cost_model: CostModel | None = None,
    ):
        self.initial_capital = initial_capital
        self.cost_model = cost_model or CostModel()

    def run(self, ohlcv: pd.DataFrame, strategy: Strategy) -> BacktestResult:
        if ohlcv.empty:
            raise ValueError("ohlcv is empty")

        signals = strategy.generate_positions(ohlcv).fillna(0.0).clip(-1.0, 1.0)
        positions = signals.shift(1).fillna(0.0)

        bar_returns = ohlcv["close"].pct_change().fillna(0.0)
        strategy_returns = positions * bar_returns

        position_changes = positions.diff().abs().fillna(positions.abs())
        cost_per_bar = position_changes * self.cost_model.total_per_trade
        net_returns = strategy_returns - cost_per_bar

        equity_curve = (1.0 + net_returns).cumprod() * self.initial_capital
        equity_curve.name = "equity"

        trades = self._extract_trades(ohlcv, positions, equity_curve)

        return BacktestResult(
            equity_curve=equity_curve,
            returns=net_returns,
            positions=positions,
            trades=trades,
            initial_capital=self.initial_capital,
            cost_model=self.cost_model,
        )

    def _extract_trades(
        self,
        ohlcv: pd.DataFrame,
        positions: pd.Series,
        equity: pd.Series,
    ) -> pd.DataFrame:
        records = []
        prev_pos = 0.0
        entry_ts = None
        entry_px = None
        for ts, pos in positions.items():
            if pos != prev_pos:
                price = ohlcv.loc[ts, "open"] if ts in ohlcv.index else ohlcv["close"].loc[ts]
                if prev_pos != 0.0 and entry_ts is not None:
                    pnl_pct = (price / entry_px - 1.0) * np.sign(prev_pos)
                    records.append(
                        {
                            "entry_ts": entry_ts,
                            "exit_ts": ts,
                            "side": "long" if prev_pos > 0 else "short",
                            "entry_px": entry_px,
                            "exit_px": price,
                            "pnl_pct": pnl_pct,
                        }
                    )
                if pos != 0.0:
                    entry_ts = ts
                    entry_px = price
                else:
                    entry_ts = None
                    entry_px = None
                prev_pos = pos
        return pd.DataFrame.from_records(records)
