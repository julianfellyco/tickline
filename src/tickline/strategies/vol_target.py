"""Volatility-targeted position sizing wrapper.

Most primary strategies return binary positions: 0 or 1. That ignores
the fact that the *same* signal in a calm market is a far smaller bet
than in a wild one, given a fixed capital base.

This wrapper scales the primary's position by `target_vol / realized_vol`,
so realized portfolio vol stays near a constant target regardless of
the asset's current regime. Leverage is capped to prevent insane
sizing when realized vol approaches zero.

  realized_vol  := rolling std of returns × √(bars_per_year)
  scale         := clip(target_vol / realized_vol, 0, max_leverage)
  out           := primary × scale, then clipped to [-max_leverage, max_leverage]

Lookback is right-aligned (uses past data only) — no lookahead.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Strategy


_DEFAULT_BARS_PER_YEAR = {
    "1m": 525_600,
    "5m": 105_120,
    "15m": 35_040,
    "1h": 8_760,
    "4h": 2_190,
    "1d": 365,
}


class VolatilityTargeted(Strategy):
    """Scale a primary strategy's positions to target annualized volatility."""

    def __init__(
        self,
        primary: Strategy,
        target_annual_vol: float = 0.15,
        lookback: int = 20,
        max_leverage: float = 2.0,
        bars_per_year: int = 8_760,
    ):
        if target_annual_vol <= 0:
            raise ValueError("target_annual_vol must be > 0")
        if lookback < 2:
            raise ValueError("lookback must be ≥ 2")
        if max_leverage <= 0:
            raise ValueError("max_leverage must be > 0")
        self.primary = primary
        self.target_annual_vol = float(target_annual_vol)
        self.lookback = int(lookback)
        self.max_leverage = float(max_leverage)
        self.bars_per_year = int(bars_per_year)
        self.name = f"vt({target_annual_vol:.2f}/{lookback})+{primary.name}"

    def generate_positions(self, ohlcv: pd.DataFrame) -> pd.Series:
        primary_pos = self.primary.generate_positions(ohlcv).fillna(0.0)
        returns = ohlcv["close"].pct_change().fillna(0.0)
        realized_vol = (
            returns.rolling(self.lookback, min_periods=self.lookback).std()
            * np.sqrt(self.bars_per_year)
        )
        scale = (self.target_annual_vol / realized_vol.replace(0, np.nan)).clip(upper=self.max_leverage)
        scale = scale.fillna(0.0)  # warmup → no exposure
        sized = (primary_pos * scale).clip(-self.max_leverage, self.max_leverage)
        sized.name = "position"
        return sized
