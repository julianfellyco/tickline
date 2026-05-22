"""Higher-timeframe trend filter.

Wrap any primary Strategy so its signals are only taken in the
direction of a slower-timeframe trend. The classic "trade with the
larger trend" rule, made explicit and testable.

Mechanics:
  - Aggregate the base OHLCV into HTF bars by grouping every `multiplier`
    bars (1h → 4× = 4h, 1h → 24× = 1D). Incomplete trailing group is
    dropped — we never read in-progress HTF bars.
  - Compute the slow SMA + slope on the HTF series.
  - Tag each HTF bar's regime as +1 / 0 / -1 (up / flat / down).
  - Project the *prior* closed HTF bar's regime onto every base bar
    via a backward as-of join. This is the no-lookahead invariant.
  - Filter the primary's positions accordingly.

Modes:
  - strict:    long signals only kept when HTF is up
               short signals only kept when HTF is down
  - long-only: long signals kept when HTF is up; all shorts dropped
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Strategy


def _htf_aggregate(ohlcv: pd.DataFrame, multiplier: int) -> pd.DataFrame:
    """Aggregate base bars into higher-timeframe bars.

    Drops the trailing partial group; HTF bars are always complete.
    """
    n = len(ohlcv)
    n_complete = (n // multiplier) * multiplier
    if n_complete == 0:
        return pd.DataFrame(columns=["open", "high", "low", "close"])

    groups = np.arange(n_complete) // multiplier
    sub = ohlcv.iloc[:n_complete]
    htf = pd.DataFrame({
        "open":  sub["open"].groupby(groups).first().values,
        "high":  sub["high"].groupby(groups).max().values,
        "low":   sub["low"].groupby(groups).min().values,
        "close": sub["close"].groupby(groups).last().values,
    }, index=sub.index[multiplier - 1::multiplier])
    return htf


class HigherTimeframeFilter(Strategy):
    """Filter a primary Strategy by a higher-timeframe trend regime."""

    MODES = ("strict", "long-only")

    def __init__(
        self,
        primary: Strategy,
        multiplier: int = 4,
        sma_period: int = 50,
        mode: str = "strict",
    ):
        if multiplier < 2:
            raise ValueError("multiplier must be ≥ 2")
        if sma_period < 2:
            raise ValueError("sma_period must be ≥ 2")
        if mode not in self.MODES:
            raise ValueError(f"mode must be one of {self.MODES}")
        self.primary = primary
        self.multiplier = int(multiplier)
        self.sma_period = int(sma_period)
        self.mode = mode
        self.name = f"htf({multiplier}x{sma_period}/{mode})+{primary.name}"

    def generate_positions(self, ohlcv: pd.DataFrame) -> pd.Series:
        primary_pos = self.primary.generate_positions(ohlcv).fillna(0.0).clip(-1.0, 1.0)
        htf = _htf_aggregate(ohlcv, self.multiplier)
        if len(htf) < self.sma_period + 2:
            # not enough HTF history → conservative: stay flat
            return pd.Series(0.0, index=ohlcv.index, name="position")

        htf_sma = htf["close"].rolling(self.sma_period).mean()
        htf_slope = htf_sma.diff()
        htf_regime = pd.Series(0, index=htf.index, dtype=int)
        htf_regime[(htf["close"] > htf_sma) & (htf_slope > 0)] = 1
        htf_regime[(htf["close"] < htf_sma) & (htf_slope < 0)] = -1
        # use *previous* closed HTF bar so we never leak the in-progress one
        htf_regime_safe = htf_regime.shift(1)

        # Backward as-of join: each base bar gets the latest HTF regime
        # whose timestamp is ≤ the base bar's timestamp.
        base_df = pd.DataFrame({"primary": primary_pos.values, "ts": ohlcv.index})
        htf_df = pd.DataFrame({"regime": htf_regime_safe.values, "ts": htf_regime_safe.index})
        # normalize dtypes for merge_asof
        htf_df["ts"] = pd.DatetimeIndex(htf_df["ts"]).astype(pd.DatetimeIndex(base_df["ts"]).dtype)
        merged = pd.merge_asof(
            base_df.sort_values("ts"),
            htf_df.sort_values("ts"),
            on="ts",
            direction="backward",
        )
        regime = merged["regime"].fillna(0).astype(int).values
        primary_arr = primary_pos.values

        out = primary_arr.copy()
        if self.mode == "strict":
            # longs only in up-regime, shorts only in down-regime
            kill_long = (primary_arr > 0) & (regime <= 0)
            kill_short = (primary_arr < 0) & (regime >= 0)
            out[kill_long] = 0.0
            out[kill_short] = 0.0
        else:  # "long-only"
            kill_long = (primary_arr > 0) & (regime <= 0)
            out[kill_long] = 0.0
            out[primary_arr < 0] = 0.0

        return pd.Series(out, index=ohlcv.index, name="position")
