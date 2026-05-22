"""RSI mean-reversion.

Buy oversold (RSI < lower), exit on neutral. Mean-reversion strategies tend
to work better in ranging regimes and get crushed in strong trends — pair
with a regime filter in production work.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Strategy


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50.0)


class RSIMeanReversion(Strategy):
    name = "rsi_meanrev"

    def __init__(self, period: int = 14, lower: float = 30.0, exit_level: float = 55.0):
        self.period = period
        self.lower = lower
        self.exit_level = exit_level

    def generate_positions(self, ohlcv: pd.DataFrame) -> pd.Series:
        rsi = _rsi(ohlcv["close"], self.period)
        positions = pd.Series(0.0, index=ohlcv.index, name="position")
        in_position = False
        for i, value in enumerate(rsi.values):
            if not in_position and value < self.lower:
                in_position = True
            elif in_position and value > self.exit_level:
                in_position = False
            positions.iloc[i] = 1.0 if in_position else 0.0
        return positions
