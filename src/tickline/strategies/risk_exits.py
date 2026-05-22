"""ATR-based stop-loss and take-profit wrapper.

The primary strategies only know how to *enter*. This wrapper adds
explicit exits: stop the trade out at `stop_atr × ATR_at_entry` against,
or take profit at `target_atr × ATR_at_entry` in our favor.

Mechanics:
  - ATR is Wilder-smoothed average true range, computed causally.
  - The ATR used for sizing each trade is *the ATR at the bar before
    entry* — no lookahead.
  - Stop / target are checked against the bar's high/low.
  - When either hits, the position is closed at the *close* of that
    bar (the engine then executes at the next open). This very slightly
    understates real slippage; for production, you'd model fills at
    the stop/target price within the bar.
  - After a stop/target exit, we stay flat until the primary's own
    signal goes back to 0 (or flips sides). Without this re-arm rule
    we'd immediately re-enter on the same stale signal.

The wrapper is a `Strategy` subclass, so it slots into the Backtester,
Portfolio, PaperRunner, and LiveRunner unchanged.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Strategy


def atr(ohlcv: pd.DataFrame, period: int = 14) -> pd.Series:
    """Wilder's Average True Range. Output aligned to ohlcv.index."""
    high = ohlcv["high"]
    low = ohlcv["low"]
    close = ohlcv["close"]
    tr = pd.concat(
        [high - low, (high - close.shift()).abs(), (low - close.shift()).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False).mean()


class StopAndTarget(Strategy):
    """Wrap any Strategy with ATR-scaled stop-loss and take-profit exits."""

    def __init__(
        self,
        primary: Strategy,
        stop_atr: float = 2.0,
        target_atr: float = 3.0,
        atr_window: int = 14,
    ):
        if stop_atr <= 0:
            raise ValueError("stop_atr must be > 0")
        if target_atr <= 0:
            raise ValueError("target_atr must be > 0")
        if atr_window < 2:
            raise ValueError("atr_window must be ≥ 2")
        self.primary = primary
        self.stop_atr = float(stop_atr)
        self.target_atr = float(target_atr)
        self.atr_window = int(atr_window)
        self.name = f"st({stop_atr:g}/{target_atr:g})+{primary.name}"

    def generate_positions(self, ohlcv: pd.DataFrame) -> pd.Series:
        primary_pos = self.primary.generate_positions(ohlcv).fillna(0.0).clip(-1.0, 1.0)
        atr_series = atr(ohlcv, self.atr_window)

        out = np.zeros(len(ohlcv), dtype=float)
        opens = ohlcv["open"].values
        highs = ohlcv["high"].values
        lows = ohlcv["low"].values
        atr_arr = atr_series.values
        primary_arr = primary_pos.values

        current_dir = 0.0
        entry_price = 0.0
        entry_atr = 0.0
        # `re_arm_at` is the position-direction value the primary must reach
        # for us to take new entries (= 0 after a forced exit, primary direction
        # otherwise). Prevents instant re-entry on the same stale signal.
        re_arm = True

        for i in range(len(ohlcv)):
            # 1) if in a trade, check stop/target on this bar
            if current_dir != 0.0:
                stop_dist = self.stop_atr * entry_atr
                tgt_dist = self.target_atr * entry_atr
                if current_dir > 0:
                    stop_price = entry_price - stop_dist
                    target_price = entry_price + tgt_dist
                    stopped = lows[i] <= stop_price
                    targeted = highs[i] >= target_price
                else:
                    stop_price = entry_price + stop_dist
                    target_price = entry_price - tgt_dist
                    stopped = highs[i] >= stop_price
                    targeted = lows[i] <= target_price

                if stopped or targeted:
                    current_dir = 0.0
                    re_arm = False  # wait for primary to confirm flat first

            # 2) if primary went flat, re-arm
            if primary_arr[i] == 0.0:
                re_arm = True
                # if we were still in a trade carried by primary, exit now
                if current_dir != 0.0:
                    current_dir = 0.0

            # 3) if flat and re-armed, follow primary's new signal
            if current_dir == 0.0 and re_arm and primary_arr[i] != 0.0:
                if i + 1 < len(ohlcv):
                    # entry executes at next open (same as backtester convention)
                    # for state-tracking we record entry price as next bar's open
                    current_dir = np.sign(primary_arr[i])
                    entry_price = opens[i + 1]
                    entry_atr = atr_arr[i] if not np.isnan(atr_arr[i]) else 0.0
                    if entry_atr <= 0:
                        # ATR not yet warmed up — defer; stay flat
                        current_dir = 0.0

            out[i] = current_dir

        return pd.Series(out, index=ohlcv.index, name="position")
