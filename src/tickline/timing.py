"""Trend timing — absolute (time-series) momentum, the simple robust kind.

One rule per asset, applied to the asset's OWN history (not ranked against
others): hold it while it's above its long moving average, sit in cash when
it's below. The documented edge is NOT bigger returns — it's much smaller
drawdowns (it gets you out before the worst of a crash).

This is deliberately separate from the cross-sectional rank engine, which
picks relative winners and was shown to be survivorship-driven. Trend
timing makes no winner picks: it just times in/out of each thing.

No lookahead: the signal is computed at the close of day t and applied to
day t+1's return (positions are shifted forward one bar).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

TRADING_DAYS = 252


@dataclass(frozen=True)
class TrendStats:
    label: str
    cagr: float        # annualized return
    vol: float         # annualized volatility
    sharpe: float
    max_dd: float      # worst peak-to-trough (negative)
    time_in: float     # fraction of days actually holding (1.0 = buy & hold)
    switches: int      # number of in/out trades


def daily_returns(close: pd.Series) -> pd.Series:
    return close.pct_change().fillna(0.0)


def trend_position(close: pd.Series, ma_window: int = 200) -> pd.Series:
    """1.0 when above the moving average, 0.0 (cash) when below — PIT-safe.

    Signal known at close of day t, acted on day t+1 (shifted), so no bar
    uses its own future.
    """
    ma = close.rolling(ma_window, min_periods=ma_window // 2).mean()
    in_trend = (close > ma).shift(1).fillna(False)
    return in_trend.astype(float)


def _equity_stats(ret: pd.Series, time_in: float, switches: int, label: str) -> TrendStats:
    ret = ret.dropna()
    n = len(ret)
    if n == 0:
        return TrendStats(label, float("nan"), 0.0, float("nan"), 0.0, time_in, switches)
    eq = (1.0 + ret).cumprod()
    final = float(eq.iloc[-1])
    cagr = final ** (TRADING_DAYS / n) - 1.0 if final > 0 else -1.0
    vol = float(ret.std() * np.sqrt(TRADING_DAYS))
    sharpe = float(ret.mean() * TRADING_DAYS / vol) if vol > 0 else float("nan")
    max_dd = float((eq / eq.cummax() - 1.0).min())
    return TrendStats(label, float(cagr), vol, sharpe, max_dd, float(time_in), int(switches))


def trend_follow(close: pd.Series, ma_window: int = 200, cost_bps: float = 5.0) -> TrendStats:
    """Hold when above the MA, cash otherwise; net of switch costs."""
    ret = daily_returns(close)
    pos = trend_position(close, ma_window)
    turn = pos.diff().abs().fillna(0.0)
    switches = int((turn > 0).sum())
    strat = pos * ret - turn * (cost_bps / 1e4)
    return _equity_stats(strat, float(pos.mean()), switches, "trend-follow")


def buy_hold(close: pd.Series) -> TrendStats:
    """Always invested — the baseline to beat (or match with less pain)."""
    return _equity_stats(daily_returns(close), 1.0, 0, "buy & hold")


def breadth(frames: dict[str, pd.DataFrame], ma_window: int = 200) -> pd.Series:
    """Fraction of assets above their MA each day — 'consensus' by counting.

    High = most things trending up together (broad agreement, risk-on).
    Low = few are (risk-off).
    """
    cols = []
    for sym, df in frames.items():
        c = df["close"]
        ma = c.rolling(ma_window, min_periods=ma_window // 2).mean()
        cols.append((c > ma).rename(sym))
    if not cols:
        return pd.Series(dtype=float)
    mat = pd.concat(cols, axis=1)
    return mat.mean(axis=1, skipna=True).rename("breadth")


def portfolio(frames: dict[str, pd.DataFrame], ma_window: int = 200,
              cost_bps: float = 5.0) -> tuple[TrendStats, TrendStats]:
    """Equal-weight basket: (trend-follow, buy & hold) over all assets.

    Trend-follow times each asset in/out independently; an asset in cash
    contributes 0 to its slice that day.
    """
    tf_cols, bh_cols, times, switches = [], [], [], 0
    for sym, df in frames.items():
        c = df["close"]
        ret = daily_returns(c)
        pos = trend_position(c, ma_window)
        turn = pos.diff().abs().fillna(0.0)
        switches += int((turn > 0).sum())
        times.append(float(pos.mean()))
        tf_cols.append((pos * ret - turn * (cost_bps / 1e4)).rename(sym))
        bh_cols.append(ret.rename(sym))
    tf = pd.concat(tf_cols, axis=1).mean(axis=1, skipna=True)
    bh = pd.concat(bh_cols, axis=1).mean(axis=1, skipna=True)
    time_in = sum(times) / len(times) if times else 0.0
    return (
        _equity_stats(tf, time_in, switches, "portfolio · trend-follow"),
        _equity_stats(bh, 1.0, 0, "portfolio · buy & hold"),
    )
