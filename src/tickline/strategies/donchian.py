"""Donchian channel breakout.

Classic trend-following (Richard Donchian, 1960s; Turtle Traders, 1980s).
Go long when price breaks above the highest high of the last N bars;
exit when price falls below the lowest low of the last M bars.

The asymmetric window (entry > exit) is the trick: enter on stronger
breakouts, exit on weaker reversals. The Turtles famously used 20/10.

Why it belongs in tickline's strategy library:
  - Different signal signature than SMA crossover (price vs channel
    instead of fast/slow MA cross) → diversifies the consensus engine
  - Discrete entry/exit triggers (not continuous) → easier to interpret
  - Performs well in trends, poorly in chop → complements RSI mean-rev
"""

from __future__ import annotations

import pandas as pd

from .base import Strategy


class DonchianBreakout(Strategy):
    """N-bar high breakout / M-bar low exit."""

    name = "donchian"

    def __init__(self, entry_window: int = 20, exit_window: int = 10, allow_short: bool = False):
        if entry_window < 2:
            raise ValueError("entry_window must be ≥ 2")
        if exit_window < 2:
            raise ValueError("exit_window must be ≥ 2")
        if exit_window > entry_window:
            raise ValueError("exit_window should be ≤ entry_window (entries on stronger break)")
        self.entry_window = int(entry_window)
        self.exit_window = int(exit_window)
        self.allow_short = bool(allow_short)
        self.name = f"donchian({entry_window}/{exit_window})"

    def generate_positions(self, ohlcv: pd.DataFrame) -> pd.Series:
        close = ohlcv["close"]
        # Use prior bars only — shift(1) so the breakout level is
        # determined by all bars *up to and including* yesterday.
        upper = close.rolling(self.entry_window).max().shift(1)
        lower = close.rolling(self.exit_window).min().shift(1)
        upper_short = close.rolling(self.entry_window).min().shift(1) if self.allow_short else None
        lower_short = close.rolling(self.exit_window).max().shift(1) if self.allow_short else None

        positions = pd.Series(0.0, index=ohlcv.index, name="position")
        current_dir = 0
        for i in range(len(close)):
            c = close.iloc[i]
            up = upper.iloc[i]
            lo = lower.iloc[i]
            if current_dir == 0:
                if pd.notna(up) and c > up:
                    current_dir = 1
                elif self.allow_short and pd.notna(upper_short.iloc[i]) and c < upper_short.iloc[i]:
                    current_dir = -1
            elif current_dir > 0:
                if pd.notna(lo) and c < lo:
                    current_dir = 0
            else:  # current_dir < 0
                if pd.notna(lower_short.iloc[i]) and c > lower_short.iloc[i]:
                    current_dir = 0
            positions.iloc[i] = float(current_dir)
        return positions
