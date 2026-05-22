"""Multi-asset / multi-strategy portfolio engine.

A `Portfolio` is a collection of `Sleeve`s. Each sleeve pairs an
exchange-fed OHLCV frame with a `Strategy` instance. The portfolio
backtest:

  1. Runs each sleeve's strategy on its own data → per-sleeve positions.
  2. Computes per-sleeve returns inside its single-asset engine
     (so fees and slippage are still real and per-leg).
  3. Combines sleeve returns into a weight DataFrame via a sizing
     method (equal, inverse-vol, vol-target, fractional Kelly).
  4. Sums weighted sleeve returns into a portfolio equity curve.

Correlation between sleeves is the silent killer of diversification.
The result object exposes the realized sleeve correlation matrix and
the contribution of each sleeve to total return.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from ..backtest.engine import Backtester, BacktestResult, CostModel
from ..strategies.base import Strategy
from .sizing import (
    SizingMethod,
    equal_weight,
    fractional_kelly,
    inverse_vol,
    vol_target,
)


@dataclass
class Sleeve:
    name: str
    ohlcv: pd.DataFrame
    strategy: Strategy


@dataclass
class PortfolioResult:
    equity_curve: pd.Series
    returns: pd.Series
    sleeve_returns: pd.DataFrame
    sleeve_weights: pd.DataFrame
    sleeve_results: dict[str, BacktestResult]
    correlation: pd.DataFrame
    initial_capital: float
    method: SizingMethod

    @property
    def final_equity(self) -> float:
        return float(self.equity_curve.iloc[-1])

    @property
    def total_return_pct(self) -> float:
        return (self.final_equity / self.initial_capital - 1.0) * 100.0

    def contributions(self) -> pd.Series:
        """Each sleeve's contribution to total portfolio return, in pp."""
        weighted = self.sleeve_weights * self.sleeve_returns
        return weighted.sum(axis=0) * 100.0


_SIZERS: dict[SizingMethod, Callable[..., pd.DataFrame]] = {
    SizingMethod.EQUAL: equal_weight,
    SizingMethod.INVERSE_VOL: inverse_vol,
    SizingMethod.VOL_TARGET: vol_target,
    SizingMethod.KELLY: fractional_kelly,
}


class Portfolio:
    def __init__(
        self,
        sleeves: list[Sleeve],
        initial_capital: float = 10_000.0,
        cost_model: CostModel | None = None,
    ):
        if not sleeves:
            raise ValueError("portfolio needs at least one sleeve")
        self.sleeves = sleeves
        self.initial_capital = initial_capital
        self.cost_model = cost_model or CostModel()

    def run(
        self,
        method: SizingMethod | str = SizingMethod.INVERSE_VOL,
        lookback: int = 30,
        **sizing_kwargs,
    ) -> PortfolioResult:
        method = SizingMethod(method)
        sizer = _SIZERS[method]

        # 1) per-sleeve backtests on aligned dates
        sleeve_results: dict[str, BacktestResult] = {}
        per_sleeve_returns: dict[str, pd.Series] = {}
        for sleeve in self.sleeves:
            bt = Backtester(
                initial_capital=self.initial_capital,
                cost_model=self.cost_model,
            )
            result = bt.run(sleeve.ohlcv, sleeve.strategy)
            sleeve_results[sleeve.name] = result
            per_sleeve_returns[sleeve.name] = result.returns

        sleeve_rets = pd.DataFrame(per_sleeve_returns).fillna(0.0)

        # 2) sizing weights (right-aligned rolling → no lookahead)
        weights = sizer(sleeve_rets, lookback=lookback, **sizing_kwargs)
        weights = weights.reindex(sleeve_rets.index).fillna(0.0)

        # shift weights by 1 bar — decision uses past info only
        weights = weights.shift(1).fillna(0.0)

        # 3) portfolio returns
        port_rets = (weights * sleeve_rets).sum(axis=1)
        equity = (1.0 + port_rets).cumprod() * self.initial_capital
        equity.name = "equity"

        # 4) realized sleeve correlation (full-sample for reporting)
        corr = sleeve_rets.corr()

        return PortfolioResult(
            equity_curve=equity,
            returns=port_rets,
            sleeve_returns=sleeve_rets,
            sleeve_weights=weights,
            sleeve_results=sleeve_results,
            correlation=corr,
            initial_capital=self.initial_capital,
            method=method,
        )
