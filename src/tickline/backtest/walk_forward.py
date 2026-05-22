"""Walk-forward validation.

In-sample backtests overfit. Walk-forward exposes that by training
(or selecting) on one window and *testing on the next, unseen one* —
then rolling forward through time.

Two modes:
  - anchored: train window grows from the start, test window slides
  - rolling: both windows are fixed-size and slide together

The validator is strategy-agnostic. Pass a `strategy_factory` callable that
builds a fresh strategy instance; if the strategy supports `.fit(train_df)`
(e.g. the meta-labeler), it's called automatically before evaluating on
the test window.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

from .engine import Backtester, BacktestResult, CostModel
from ..risk import PerformanceMetrics, compute_metrics
from ..strategies.base import Strategy


@dataclass
class WindowResult:
    window_id: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    metrics: PerformanceMetrics
    backtest: BacktestResult


@dataclass
class WalkForwardResult:
    windows: list[WindowResult] = field(default_factory=list)
    timeframe: str = "1h"

    def summary(self) -> pd.DataFrame:
        rows = [
            {
                "window": w.window_id,
                "train_end": w.train_end.strftime("%Y-%m-%d"),
                "test_start": w.test_start.strftime("%Y-%m-%d"),
                "test_end": w.test_end.strftime("%Y-%m-%d"),
                "return_pct": w.metrics.total_return_pct,
                "sharpe": w.metrics.sharpe,
                "max_dd_pct": w.metrics.max_drawdown_pct,
                "trades": w.metrics.num_trades,
                "win_rate": w.metrics.win_rate_pct,
            }
            for w in self.windows
        ]
        return pd.DataFrame(rows)

    def aggregate_sharpe(self) -> float:
        if not self.windows:
            return 0.0
        return float(sum(w.metrics.sharpe for w in self.windows) / len(self.windows))

    def aggregate_return_pct(self) -> float:
        if not self.windows:
            return 0.0
        return float(sum(w.metrics.total_return_pct for w in self.windows) / len(self.windows))

    def sharpe_consistency(self) -> float:
        """Fraction of windows with positive Sharpe.

        Closer to 1.0 = strategy works robustly across regimes.
        Closer to 0.5 = strategy is essentially coin-flipping.
        """
        if not self.windows:
            return 0.0
        positive = sum(1 for w in self.windows if w.metrics.sharpe > 0)
        return positive / len(self.windows)


def run_walk_forward(
    ohlcv: pd.DataFrame,
    strategy_factory: Callable[[], Strategy],
    train_bars: int,
    test_bars: int,
    mode: str = "anchored",
    cost_model: CostModel | None = None,
    initial_capital: float = 10_000.0,
    timeframe: str = "1h",
    min_train_bars: int | None = None,
) -> WalkForwardResult:
    """Run walk-forward validation.

    Args:
        ohlcv: full price history with timestamp index.
        strategy_factory: zero-arg callable returning a fresh Strategy instance
            each window. Strategies that need calibration must implement
            `.fit(train_df)`.
        train_bars: size of the initial training window in bars.
        test_bars: size of each test window in bars.
        mode: "anchored" (train window grows) or "rolling" (fixed-size).
        cost_model: transaction cost model passed to the per-window backtester.
        initial_capital: starting capital each window — windows are independent,
            we do not compound across them.
        timeframe: bar timeframe; used for annualization in metrics.
        min_train_bars: lower bound on train size; defaults to train_bars.
    """
    if mode not in {"anchored", "rolling"}:
        raise ValueError("mode must be 'anchored' or 'rolling'")
    if len(ohlcv) < train_bars + test_bars:
        raise ValueError(
            f"need at least {train_bars + test_bars} bars, got {len(ohlcv)}"
        )

    cost_model = cost_model or CostModel()
    min_train_bars = min_train_bars or train_bars

    results: list[WindowResult] = []
    test_start = train_bars
    window_id = 0
    while test_start + test_bars <= len(ohlcv):
        if mode == "anchored":
            train_slice = ohlcv.iloc[: test_start]
        else:
            train_slice = ohlcv.iloc[test_start - train_bars : test_start]
        test_slice = ohlcv.iloc[test_start : test_start + test_bars]

        if len(train_slice) < min_train_bars:
            test_start += test_bars
            continue

        strategy = strategy_factory()
        fit = getattr(strategy, "fit", None)
        if callable(fit):
            try:
                fit(train_slice)
            except ValueError:
                test_start += test_bars
                continue

        bt = Backtester(initial_capital=initial_capital, cost_model=cost_model)
        result = bt.run(test_slice, strategy)
        metrics = compute_metrics(
            result.returns, result.equity_curve, result.trades, timeframe
        )

        results.append(
            WindowResult(
                window_id=window_id,
                train_start=train_slice.index[0],
                train_end=train_slice.index[-1],
                test_start=test_slice.index[0],
                test_end=test_slice.index[-1],
                metrics=metrics,
                backtest=result,
            )
        )
        window_id += 1
        test_start += test_bars

    return WalkForwardResult(windows=results, timeframe=timeframe)
