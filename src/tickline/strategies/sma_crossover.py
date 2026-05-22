"""Simple Moving Average crossover.

Classic baseline: go long when the fast SMA crosses above the slow SMA,
flat (or short if enabled) when it crosses below. Useful as a sanity check
and a benchmark to beat. Most edge in this kind of trend filter comes from
position sizing and exit rules, not the signal itself.
"""

from __future__ import annotations

import pandas as pd

from .base import Strategy


class SMACrossover(Strategy):
    name = "sma_crossover"

    def __init__(self, fast: int = 20, slow: int = 50, allow_short: bool = False):
        if fast >= slow:
            raise ValueError("fast period must be < slow period")
        self.fast = fast
        self.slow = slow
        self.allow_short = allow_short

    def generate_positions(self, ohlcv: pd.DataFrame) -> pd.Series:
        close = ohlcv["close"]
        fast_sma = close.rolling(self.fast).mean()
        slow_sma = close.rolling(self.slow).mean()

        long_signal = (fast_sma > slow_sma).astype(float)
        if self.allow_short:
            positions = long_signal - (fast_sma < slow_sma).astype(float)
        else:
            positions = long_signal

        positions[: self.slow] = 0.0
        positions.name = "position"
        return positions
