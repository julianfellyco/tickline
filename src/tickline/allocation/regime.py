"""Regime classifier.

Tags each bar as TREND_UP, TREND_DOWN, or RANGE based on lookback-window
return relative to recent volatility. A simple, interpretable classifier
that captures most of the value institutions extract from fancier
methods — see Lo & Hasanhodzic, *The Heretics of Finance*.

Two thresholds:
  - trend_threshold (in units of stddev): how much rolling return must
    exceed recent volatility to call a trend
  - This is intentionally crude. In production you'd add ADX, ATR, and
    a confirmation filter, but the *shape* of the classifier matters
    more than the specific indicators.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import pandas as pd


class Regime(str, Enum):
    TREND_UP = "trend_up"
    TREND_DOWN = "trend_down"
    RANGE = "range"


@dataclass
class RegimeClassifier:
    lookback: int = 50
    vol_window: int = 20
    trend_threshold: float = 1.0  # in units of rolling vol

    def classify(self, ohlcv: pd.DataFrame) -> pd.Series:
        """Return a Series of Regime values aligned to ohlcv.index."""
        close = ohlcv["close"]
        rolling_return = close.pct_change(self.lookback)
        rolling_vol = close.pct_change().rolling(self.vol_window).std()

        # threshold in absolute return space: vol * trend_threshold
        threshold = rolling_vol * self.trend_threshold

        regimes = pd.Series([Regime.RANGE] * len(ohlcv), index=ohlcv.index, dtype=object)
        up = rolling_return > threshold
        down = rolling_return < -threshold
        regimes[up] = Regime.TREND_UP
        regimes[down] = Regime.TREND_DOWN
        # NaN periods stay as RANGE (default)
        regimes.name = "regime"
        return regimes

    def regime_durations(self, ohlcv: pd.DataFrame) -> pd.Series:
        """How many bars each regime occupies — for reporting."""
        regs = self.classify(ohlcv)
        return regs.value_counts()
