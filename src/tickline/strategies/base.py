"""Strategy base class.

A strategy turns OHLCV data into a target position series:
  +1.0 = fully long
   0.0 = flat
  -1.0 = fully short
Values between are partial sizing.

The backtest engine takes care of fills, fees, and PnL.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import pandas as pd


class Strategy(ABC):
    name: str = "base"

    @abstractmethod
    def generate_positions(self, ohlcv: pd.DataFrame) -> pd.Series:
        """Return a target-position series aligned to ohlcv.index.

        Values must be in [-1, 1]. The engine evaluates the position at the
        close of each bar and executes at the next bar's open (no lookahead).
        """
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"<Strategy: {self.name}>"
